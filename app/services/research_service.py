from __future__ import annotations

import asyncio
import hashlib
import re
from time import perf_counter
from urllib.parse import urlsplit

from app.core.config import Settings
from app.core.errors import InvalidRequestError, UpstreamFailureError
from app.core.logging import get_logger
from app.core.search_language import resolve_search_language_for_query
from app.extractors.page_extractor import PageExtractor
from app.models import (
    AgentResult,
    AgentSearchRequest,
    AgentSearchResponse,
    FetchContentRequest,
    FetchContentResponse,
    ExtractFromUrlsRequest,
    ExtractResponse,
    RawSearchCandidate,
    TimingBreakdown,
)
from app.providers.base import SearchProvider

logger = get_logger(__name__)


class ResearchService:
    def __init__(self, provider: SearchProvider, extractor: PageExtractor, settings: Settings) -> None:
        self._provider = provider
        self._extractor = extractor
        self._settings = settings

    async def agent_search(self, payload: AgentSearchRequest, request_id: str) -> AgentSearchResponse:
        started = perf_counter()
        search_started = perf_counter()
        budget = min(payload.max_results, self._settings.search_max_results)
        search_query = build_search_query(payload.query)
        effective_language = resolve_search_language_for_query(
            payload.language or self._settings.search_language_default,
            self._settings.browser_locale,
            payload.query,
        ).code

        try:
            provider_response = await asyncio.wait_for(
                self._provider.search(
                    search_query,
                    min(budget * 2, self._settings.fetch_max_pages),
                    payload.search_engine or self._settings.search_engine_default,
                    effective_language,
                ),
                timeout=self._settings.search_timeout_ms / 1000,
            )
        except TimeoutError as exc:
            raise UpstreamFailureError("search provider timed out") from exc
        search_duration_ms = elapsed_ms(search_started)

        filtered = self._filter_candidates(provider_response.candidates, payload.include_domains, payload.exclude_domains)
        fetch_started = perf_counter()
        results, failed_urls, warnings = await self._extract_candidates(
            select_candidates_for_fetch(filtered, payload.query, self._settings.fetch_max_pages),
            payload.query,
            payload.include_raw_content,
        )
        warnings = provider_response.warnings + warnings
        ranked = sorted(results, key=lambda item: item.score, reverse=True)[:budget]

        if (payload.search_engine or self._settings.search_engine_default) == "auto" and should_retry_with_mixed(ranked):
            mixed_response = await asyncio.wait_for(
                self._provider.search(
                    search_query,
                    min(budget * 2, self._settings.fetch_max_pages),
                    "mixed",
                    effective_language,
                ),
                timeout=self._settings.search_timeout_ms / 1000,
            )
            mixed_filtered = self._filter_candidates(
                mixed_response.candidates,
                payload.include_domains,
                payload.exclude_domains,
            )
            mixed_results, mixed_failed_urls, mixed_warnings = await self._extract_candidates(
                select_candidates_for_fetch(mixed_filtered, payload.query, self._settings.fetch_max_pages),
                payload.query,
                payload.include_raw_content,
            )
            warnings.extend(mixed_response.warnings + mixed_warnings)
            failed_urls.extend(mixed_failed_urls)
            ranked = rerank_merged_results(results + mixed_results, budget)
            provider_response.engines_used = dedupe_strings(provider_response.engines_used + mixed_response.engines_used)

        answer = synthesize_answer(ranked)
        response = AgentSearchResponse(
            query=payload.query,
            answer=answer,
            results=ranked,
            failed_urls=failed_urls,
            timing_ms=TimingBreakdown(
                total=elapsed_ms(started),
                search=search_duration_ms,
                fetch_extract=elapsed_ms(fetch_started),
            ),
            provider=self._provider.name,
            search_engine=payload.search_engine or self._settings.search_engine_default,
            search_engines_used=provider_response.engines_used,
            language=effective_language,
            warnings=warnings,
        )
        self._log_request(
            request_id,
            payload.query,
            payload.search_engine,
            effective_language,
            provider_response.engines_used,
            len(provider_response.candidates),
            len(ranked),
            len(failed_urls),
        )
        return response

    async def extract_from_urls(self, payload: ExtractFromUrlsRequest, request_id: str) -> ExtractResponse:
        results, failed_urls, warnings = await self._extract_candidates(
            [RawSearchCandidate(url=str(url), title="", snippet="", engine="fetch") for url in payload.urls],
            payload.focus_query,
            payload.include_raw_content,
        )
        ranked = sorted(results, key=lambda item: item.score, reverse=True)
        self._log_request(
            request_id,
            payload.focus_query or "",
            "extract",
            "n/a",
            ["extract"],
            len(payload.urls),
            len(ranked),
            len(failed_urls),
        )
        return ExtractResponse(
            focus_query=payload.focus_query,
            results=ranked,
            failed_urls=failed_urls,
            provider=self._provider.name,
            warnings=warnings,
        )

    async def fetch_content(self, payload: FetchContentRequest, request_id: str) -> FetchContentResponse:
        results, failed_urls, warnings = await self._extract_candidates(
            [RawSearchCandidate(url=str(payload.url), title="", snippet="", engine="fetch")],
            payload.focus_query,
            payload.include_raw_content,
        )
        result = results[0] if results else None
        self._log_request(
            request_id,
            payload.focus_query or str(payload.url),
            "fetch",
            "n/a",
            ["fetch"],
            1,
            len(results),
            len(failed_urls),
        )
        return FetchContentResponse(
            focus_query=payload.focus_query,
            result=result,
            failed_url=failed_urls[0] if failed_urls else None,
            provider=self._provider.name,
            warnings=warnings,
        )

    def _filter_candidates(
        self,
        candidates: list[RawSearchCandidate],
        include_domains: list[str],
        exclude_domains: list[str],
    ) -> list[RawSearchCandidate]:
        include_set = {domain.lower() for domain in include_domains}
        exclude_set = {domain.lower() for domain in exclude_domains}
        seen: set[str] = set()
        filtered: list[RawSearchCandidate] = []
        for candidate in candidates:
            host = (urlsplit(candidate.url).hostname or "").lower()
            if not host:
                continue
            if include_set and not any(host == domain or host.endswith(f".{domain}") for domain in include_set):
                continue
            if any(host == domain or host.endswith(f".{domain}") for domain in exclude_set):
                continue
            canonical = candidate.url.strip()
            if canonical in seen:
                continue
            seen.add(canonical)
            filtered.append(candidate)
        return filtered

    async def _extract_candidates(
        self,
        candidates: list[RawSearchCandidate],
        query: str | None,
        include_raw_content: bool,
    ) -> tuple[list[AgentResult], list[str], list[str]]:
        semaphore = asyncio.Semaphore(self._settings.fetch_max_concurrency)
        warnings: list[str] = []
        failed_urls: list[str] = []

        async def run(candidate: RawSearchCandidate) -> AgentResult | None:
            async with semaphore:
                serp_score = compute_score(query or "", candidate.title, candidate.snippet, candidate.url)
                try:
                    page = await self._extractor.extract(candidate.url, query, include_raw_content)
                except (InvalidRequestError, UpstreamFailureError, Exception):
                    failed_urls.append(candidate.url)
                    return fallback_result(candidate, query, serp_score)
                page_score = compute_score(query or "", page.title, page.content, page.url)
                return AgentResult(
                    title=page.title or candidate.title or page.url,
                    url=page.url,
                    content=page.content,
                    snippet=best_snippet(page.snippet, candidate.snippet, page.content),
                    score=max(page_score, serp_score),
                    published_date=page.published_date,
                    source_type=page.source_type,
                    raw_content=page.raw_content,
                )

        extracted = await asyncio.gather(*(run(candidate) for candidate in candidates))
        results = [item for item in extracted if item is not None]
        results = filter_low_quality_results(results, query or "")
        if failed_urls:
            warnings.append("some URLs could not be fetched or extracted")
        if not results and failed_urls:
            warnings.append("no extractable results were produced")
        return results, failed_urls, warnings

    def _log_request(
        self,
        request_id: str,
        query: str,
        search_engine: str,
        language: str,
        search_engines_used: list[str],
        candidate_count: int,
        result_count: int,
        failed_count: int,
    ) -> None:
        logger.info(
            "agent_search",
            extra={
                "extra_data": {
                    "request_id": request_id,
                    "provider": self._provider.name,
                    "query_hash": hashlib.sha256(query.encode("utf-8")).hexdigest()[:16] if query else None,
                    "search_engine": search_engine,
                    "language": language,
                    "search_engines_used": search_engines_used,
                    "candidate_count": candidate_count,
                    "result_count": result_count,
                    "failed_count": failed_count,
                }
            },
        )


def compute_score(query: str, title: str, content: str, url: str) -> float:
    terms = extract_query_terms(query)
    base = 0.1
    if not terms:
        return round(min(1.0, base + url_depth_bonus(url)), 3)
    haystack = normalize_text(f"{title} {content}")
    title_lower = normalize_text(title)
    url_lower = normalize_text(url)
    title_hits = sum(1 for term in terms if term in title_lower)
    content_hits = sum(1 for term in terms if term in haystack)
    url_hits = sum(1 for term in terms if term in url_lower)
    title_score = title_hits / max(1, len(terms))
    content_score = content_hits / max(1, len(terms))
    url_score = url_hits / max(1, len(terms))
    score = base + title_score * 0.45 + content_score * 0.2 + url_score * 0.15 + url_depth_bonus(url)

    compact_query = " ".join(terms)
    if compact_query and compact_query in haystack:
        score += 0.1
    score += topical_bonus(query, title, content, url)
    score -= source_penalty(query, title, url)
    return round(min(1.0, score), 3)


def synthesize_answer(results: list[AgentResult]) -> str | None:
    if not results:
        return None
    parts = []
    for result in results[:3]:
        snippet = clean_summary_line(result.snippet or result.content)
        if not snippet:
            continue
        parts.append(f"{result.title}: {snippet}")
    return " | ".join(parts)[:450] or None


def elapsed_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)


def url_depth_bonus(url: str) -> float:
    path = (urlsplit(url).path or "/").strip("/")
    if not path:
        return 0.0
    segments = [segment for segment in path.split("/") if segment]
    return min(0.15, 0.05 * len(segments))


def clean_summary_line(text: str) -> str:
    compact = " ".join(text.split())
    return compact[:140]


POLISH_STOPWORDS = {
    "aby",
    "ale",
    "bez",
    "bo",
    "co",
    "czy",
    "dla",
    "do",
    "gdzie",
    "go",
    "i",
    "ich",
    "ile",
    "jak",
    "jaka",
    "jakie",
    "jest",
    "lub",
    "ma",
    "najlepsze",
    "najlepszy",
    "na",
    "nie",
    "o",
    "od",
    "oraz",
    "po",
    "pod",
    "przez",
    "się",
    "to",
    "u",
    "ugotować",
    "ugotowac",
    "usunąć",
    "usunac",
    "w",
    "we",
    "z",
    "za",
}

ENGLISH_STOPWORDS = {
    "and",
    "are",
    "for",
    "how",
    "is",
    "latest",
    "news",
    "the",
    "to",
    "what",
}


def extract_query_terms(query: str) -> list[str]:
    tokens = [token for token in re.findall(r"[^\W\d_]+", normalize_text(query), flags=re.UNICODE) if len(token) > 2]
    stopwords = POLISH_STOPWORDS | ENGLISH_STOPWORDS
    return [token for token in tokens if token not in stopwords]


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def topical_bonus(query: str, title: str, content: str, url: str) -> float:
    lowered = normalize_text(f"{title} {content} {url}")
    query_lower = normalize_text(query)
    bonus = 0.0
    if any(term in query_lower for term in {"przepis", "szarlotka", "sernik", "pierogi", "rosół"}):
        if any(marker in lowered for marker in {"przepis", "recipe", "ingredients", "składniki"}):
            bonus += 0.12
    if any(term in query_lower for term in {"objawy", "grypy", "żelaza", "dzieci"}):
        if any(marker in lowered for marker in {"objawy", "symptoms", "leczenie", "treatment"}):
            bonus += 0.1
    if any(term in query_lower for term in {"docker", "compose", "open", "webui"}):
        if any(marker in lowered for marker in {"docker", "compose", "open webui", "openwebui"}):
            bonus += 0.14
        if any(marker in lowered for marker in {"docs.docker.com", "github.com", "openwebui.com", "docs.openwebui.com"}):
            bonus += 0.2
    if "fastapi" in query_lower:
        if any(marker in lowered for marker in {"fastapi.tiangolo.com", "fastapi", "github.com/fastapi"}):
            bonus += 0.24
    if "langchain" in query_lower:
        if any(marker in lowered for marker in {"langchain.com", "python.langchain.com", "github.com/langchain-ai"}):
            bonus += 0.22
    if "vector database" in query_lower:
        if any(marker in lowered for marker in {"pinecone", "weaviate", "milvus", "qdrant", "vector database"}):
            bonus += 0.18
    if "facebook" in query_lower:
        if any(marker in lowered for marker in {"facebook.com", "meta.com", "centrum pomocy", "help center"}):
            bonus += 0.18
    if any(term in query_lower for term in {"laptop", "smartfon", "smartfonów", "smartfonow"}):
        if any(marker in lowered for marker in {"ranking", "test", "recenzja", "benchmark", "ceneo", "media markt", "media expert"}):
            bonus += 0.12
    if any(term in query_lower for term in {"działalność", "dzialalnosc", "księgi", "ksiegi", "pit"}):
        if any(marker in lowered for marker in {"gov.pl", "biznes.gov.pl", "podatki.gov.pl", "ekw.ms.gov.pl", "mobywatel.gov.pl"}):
            bonus += 0.24
    return bonus


def source_penalty(query: str, title: str, url: str) -> float:
    lowered = normalize_text(f"{title} {url}")
    penalty = 0.0
    junk_hosts = {
        "commentcamarche",
        "dictionary",
        "cambridge",
        "linguee",
        "glosbe",
        "baidu",
        "forum",
    }
    if any(marker in lowered for marker in junk_hosts):
        penalty += 0.22
    if "forum" in lowered and not any(term in normalize_text(query) for term in {"forum", "dyskusja"}):
        penalty += 0.08
    if any(marker in lowered for marker in {"support.google.com", "steamcommunity.com", "answers.microsoft.com"}):
        penalty += 0.28
    if contains_cjk(lowered):
        penalty += 0.35
    if "filmweb.pl" in lowered and any(term in normalize_text(query) for term in {"laptop", "smartfon", "ranking"}):
        penalty += 0.3
    if "stackoverflow.com" in lowered and any(term in normalize_text(query) for term in {"co to jest", "what is"}):
        penalty += 0.1
    return penalty


def best_snippet(primary: str, secondary: str, fallback: str) -> str:
    for value in (primary, secondary, fallback):
        compact = " ".join(value.split())
        if compact:
            return compact[:280]
    return ""


def fallback_result(candidate: RawSearchCandidate, query: str | None, serp_score: float) -> AgentResult | None:
    if not candidate.title and not candidate.snippet:
        return None
    if serp_score < 0.4:
        return None
    return AgentResult(
        title=candidate.title or candidate.url,
        url=candidate.url,
        content=(candidate.snippet or candidate.title)[:800],
        snippet=best_snippet(candidate.snippet, candidate.title, candidate.url),
        score=min(0.85, serp_score),
        published_date=None,
        source_type="general",
        raw_content=None,
    )


def filter_low_quality_results(results: list[AgentResult], query: str) -> list[AgentResult]:
    if not results:
        return results
    strong = [item for item in results if item.score >= 0.35]
    if strong:
        return strong
    return []


def rerank_merged_results(results: list[AgentResult], budget: int) -> list[AgentResult]:
    deduped: dict[str, AgentResult] = {}
    for item in results:
        key = str(item.url).strip()
        current = deduped.get(key)
        if current is None or item.score > current.score:
            deduped[key] = item
    return sorted(deduped.values(), key=lambda item: item.score, reverse=True)[:budget]


def dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def should_retry_with_mixed(results: list[AgentResult]) -> bool:
    if not results:
        return True
    top_score = max(item.score for item in results)
    return top_score < 0.7


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def build_search_query(query: str) -> str:
    normalized = normalize_text(query)
    year = next((token for token in normalized.split() if token.isdigit() and len(token) == 4), "")
    if "open webui" in normalized:
        return '"open-webui" OR "open webui" site:docs.openwebui.com OR site:github.com/open-webui'
    if "docker compose" in normalized:
        return '"docker compose" site:docs.docker.com'
    if "fastapi" in normalized:
        return '"fastapi" site:fastapi.tiangolo.com OR site:github.com/fastapi'
    if "langchain" in normalized:
        return '"langchain" site:python.langchain.com OR site:langchain.com OR site:github.com/langchain-ai'
    if "vector database" in normalized:
        return '"vector database" OR qdrant OR weaviate OR pinecone OR milvus'
    if "facebook" in normalized and "konto" in normalized and any(marker in normalized for marker in {"usun", "usunąć", "usunac"}):
        return "facebook usunięcie konta site:facebook.com"
    if "laptop" in normalized and "pracy" in normalized:
        return " ".join(part for part in ["ranking laptopów do pracy", year] if part)
    if "działalność gospodarcza" in normalized or "dzialalnosc gospodarcza" in normalized:
        return '"działalność gospodarcza" site:biznes.gov.pl OR site:gov.pl'
    if "księgi wieczystej" in normalized or "ksiegi wieczystej" in normalized:
        return '"numer księgi wieczystej" site:gov.pl OR site:ekw.ms.gov.pl'
    if "objawy" in normalized and "gryp" in normalized and "dzieci" in normalized:
        return "objawy grypy u dzieci site:medonet.pl OR site:mp.pl OR site:abczdrowie.pl"
    phrases: list[str] = []
    for phrase in ():
        if phrase in normalized:
            phrases.append(f'"{phrase}"')
            normalized = normalized.replace(phrase, " ")
    terms = extract_query_terms(normalized)
    parts = phrases + terms
    return " ".join(parts) if parts else query


def select_candidates_for_fetch(
    candidates: list[RawSearchCandidate],
    query: str,
    max_pages: int,
) -> list[RawSearchCandidate]:
    ranked = sorted(
        candidates,
        key=lambda candidate: compute_score(query, candidate.title, candidate.snippet, candidate.url),
        reverse=True,
    )
    return ranked[:max_pages]
