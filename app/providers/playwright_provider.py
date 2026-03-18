from __future__ import annotations

import base64
from contextlib import suppress
from dataclasses import dataclass
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit

from app.core.config import Settings
from app.core.errors import UpstreamFailureError
from app.core.search_engines import normalize_search_engine, resolve_engine_plan, should_stop_after_success
from app.core.search_language import SearchLanguage, resolve_search_language
from app.models import RawSearchCandidate, SearchProviderResponse
from app.providers.base import SearchProvider

try:
    from playwright.async_api import Browser, Error as PlaywrightError, Page, TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover
    Browser = object  # type: ignore[assignment]
    Page = object  # type: ignore[assignment]
    PlaywrightError = RuntimeError  # type: ignore[assignment]
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]
    async_playwright = None  # type: ignore[assignment]


class EngineUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class EngineSpec:
    name: str
    host: str


ENGINE_SPECS = {
    "bing": EngineSpec("bing", "www.bing.com"),
    "brave": EngineSpec("brave", "search.brave.com"),
    "google": EngineSpec("google", "www.google.com"),
    "duckduckgo": EngineSpec("duckduckgo", "html.duckduckgo.com"),
}


class PlaywrightSearchProvider(SearchProvider):
    name = "playwright-meta"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def search(self, query: str, count: int, search_engine: str, language: str) -> SearchProviderResponse:
        if async_playwright is None:
            raise UpstreamFailureError("playwright is not installed")
        if not self._settings.browser_enabled:
            raise UpstreamFailureError("browser provider is disabled")

        requested_engine = normalize_search_engine(search_engine or self._settings.search_engine_default)
        resolved_language = resolve_search_language(language or self._settings.search_language_default, self._settings.browser_locale)
        plan = resolve_engine_plan(requested_engine)
        warnings: list[str] = []
        engines_used: list[str] = []
        merged: list[RawSearchCandidate] = []
        seen: set[str] = set()

        for engine_name in plan:
            try:
                engine_results = await self._search_single_engine(query, count, engine_name, resolved_language)
            except UpstreamFailureError as exc:
                if requested_engine in {"auto", "mixed", "all"}:
                    warnings.append(f"{engine_name} unavailable: {exc.message}")
                    continue
                raise

            if engine_results:
                engines_used.append(engine_name)
            for candidate in engine_results:
                key = candidate.url.strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                merged.append(candidate)

            if should_stop_after_success(
                requested_engine,
                len(merged),
                count,
                has_sufficient_depth=has_sufficient_depth_results(merged),
            ):
                break

        if requested_engine not in {"auto", "mixed", "all"} and not merged:
            raise UpstreamFailureError(f"{requested_engine} produced no usable results")

        return SearchProviderResponse(candidates=merged[: max(count * 2, count)], engines_used=engines_used, warnings=warnings)

    async def _search_single_engine(
        self,
        query: str,
        count: int,
        engine_name: str,
        language: SearchLanguage,
    ) -> list[RawSearchCandidate]:
        spec = ENGINE_SPECS[engine_name]
        browser: Browser | None = None
        context = None
        page = None

        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=self._settings.browser_headless,
                    args=["--disable-dev-shm-usage"],
                    proxy=self._build_browser_proxy(spec.host),
                )
                context = await browser.new_context(
                    locale=language.locale,
                    user_agent=self._settings.browser_user_agent,
                    extra_http_headers={"Accept-Language": language.accept_language},
                )
                page = await context.new_page()
                page.set_default_navigation_timeout(self._settings.browser_timeout_ms)
                await page.route("**/*", self._route_request)
                await page.goto(
                    self._build_search_url(spec, query, language),
                    wait_until="domcontentloaded",
                    timeout=self._settings.browser_timeout_ms,
                )
                return await self._extract_results(engine_name, page, count)
        except EngineUnavailableError as exc:
            raise UpstreamFailureError(str(exc)) from exc
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            raise UpstreamFailureError(str(exc)) from exc
        finally:
            if page is not None:
                with suppress(Exception):
                    await page.close()
            if context is not None:
                with suppress(Exception):
                    await context.close()
            if browser is not None:
                with suppress(Exception):
                    await browser.close()

    async def _route_request(self, route) -> None:
        if route.request.resource_type in {"image", "media", "font"}:
            await route.abort()
            return
        await route.continue_()

    async def _extract_results(self, engine_name: str, page: Page, count: int) -> list[RawSearchCandidate]:
        title = ((await page.title()) or "").strip().lower()
        content = ((await page.content()) or "")[:12000].lower()
        if engine_name == "google" and ("about this page" in content or "recaptcha" in content):
            raise EngineUnavailableError("google presented an anti-bot challenge")
        if engine_name == "brave" and "captcha - brave search" in title:
            raise EngineUnavailableError("brave presented a captcha challenge")
        if engine_name == "duckduckgo" and ("bots use duckduckgo too" in content or "anomaly-modal" in content):
            raise EngineUnavailableError("duckduckgo presented an anti-bot challenge")

        if engine_name == "bing":
            return await self._extract_bing_results(page, count)
        if engine_name == "google":
            return await self._extract_generic_results(
                page,
                count,
                "div.g",
                ["div.yuRUbf a", "a[href^='http']"],
                [".VwiC3b", ".aCOpRe", "div[data-sncf='1']"],
                engine_name,
            )
        if engine_name == "brave":
            return await self._extract_generic_results(
                page,
                count,
                "div[data-type='web']",
                ["a[href^='http']"],
                ["div.snippet-description", "div.snippet-content", "p"],
                engine_name,
            )
        return await self._extract_generic_results(
            page,
            count,
            ".result",
            ["a.result__a", "a[href^='http']"],
            [".result__snippet", ".snippet"],
            engine_name,
        )

    async def _extract_bing_results(self, page: Page, count: int) -> list[RawSearchCandidate]:
        items = page.locator("li.b_algo")
        found = await items.count()
        if found == 0:
            return []

        results: list[RawSearchCandidate] = []
        limit = min(found, count * 4)
        for index in range(limit):
            item = items.nth(index)
            title_link = item.locator("h2 a").first
            if await title_link.count() == 0:
                continue
            href = await title_link.get_attribute("href")
            title = (await title_link.text_content() or "").strip()
            snippet_locator = item.locator(".b_caption p").first
            snippet = ((await snippet_locator.text_content()) or "").strip() if await snippet_locator.count() else ""
            resolved_href = decode_bing_url(href)
            if not resolved_href or not title:
                continue
            results.append(RawSearchCandidate(url=resolved_href, title=title, snippet=snippet, engine="bing"))
        return results

    async def _extract_generic_results(
        self,
        page: Page,
        count: int,
        item_selector: str,
        link_selectors: list[str],
        snippet_selectors: list[str],
        engine_name: str,
    ) -> list[RawSearchCandidate]:
        items = page.locator(item_selector)
        found = await items.count()
        results: list[RawSearchCandidate] = []

        if found:
            limit = min(found, count * 4)
            for index in range(limit):
                item = items.nth(index)
                candidate = await self._extract_candidate_from_node(item, link_selectors, snippet_selectors, engine_name)
                if candidate is not None:
                    results.append(candidate)

        if results:
            return results

        anchors = page.locator("a[href^='http']")
        anchor_count = min(await anchors.count(), count * 8)
        for index in range(anchor_count):
            anchor = anchors.nth(index)
            href = await anchor.get_attribute("href")
            title = (await anchor.text_content() or "").strip()
            if not href or len(title) < 8:
                continue
            if "google.com" in href or "bing.com" in href or "search.brave.com" in href or "duckduckgo.com" in href:
                continue
            results.append(RawSearchCandidate(url=href, title=title, snippet="", engine=engine_name))
            if len(results) >= count:
                break
        return results

    async def _extract_candidate_from_node(
        self,
        node,
        link_selectors: list[str],
        snippet_selectors: list[str],
        engine_name: str,
    ) -> RawSearchCandidate | None:
        title_link = None
        for selector in link_selectors:
            locator = node.locator(selector).first
            if await locator.count():
                title_link = locator
                break
        if title_link is None:
            return None

        href = await title_link.get_attribute("href")
        title = (await title_link.text_content() or "").strip()
        if not href or not title:
            return None

        snippet = ""
        for selector in snippet_selectors:
            locator = node.locator(selector).first
            if await locator.count():
                snippet = ((await locator.text_content()) or "").strip()
                if snippet:
                    break

        return RawSearchCandidate(url=href, title=title, snippet=snippet, engine=engine_name)

    def _build_browser_proxy(self, host: str) -> dict[str, str] | None:
        if should_bypass_proxy(host, self._settings.no_proxy):
            return None
        proxy_server = self._settings.https_proxy or self._settings.http_proxy
        if not proxy_server:
            return None
        return {"server": proxy_server}

    def _build_search_url(self, spec: EngineSpec, query: str, language: SearchLanguage) -> str:
        encoded_query = quote_plus(query)
        if spec.name == "bing":
            return (
                f"https://www.bing.com/search?q={encoded_query}"
                f"&setlang={quote_plus(language.language)}"
                f"&mkt={quote_plus(language.locale)}"
            )
        if spec.name == "google":
            return (
                f"https://www.google.com/search?q={encoded_query}"
                f"&hl={quote_plus(language.language)}"
                f"&gl={quote_plus(language.region)}"
            )
        if spec.name == "duckduckgo":
            return f"https://html.duckduckgo.com/html/?q={encoded_query}&kl={quote_plus(language.duckduckgo_kl)}"
        return (
            f"https://search.brave.com/search?q={encoded_query}"
            f"&source=web"
            f"&lang={quote_plus(language.language)}"
            f"&country={quote_plus(language.region.lower())}"
        )


def decode_bing_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url)
    if parsed.netloc != "www.bing.com" or not parsed.path.startswith("/ck/a"):
        return url
    encoded = parse_qs(parsed.query).get("u", [None])[0]
    if not encoded:
        return url
    decoded = decode_bing_target(encoded)
    return decoded or url


def decode_bing_target(value: str) -> str | None:
    candidate = unquote(value)
    if candidate.startswith("a1"):
        candidate = candidate[2:]
    padding = "=" * (-len(candidate) % 4)
    try:
        raw = base64.urlsafe_b64decode(candidate + padding).decode("utf-8", errors="ignore")
    except Exception:
        return None
    return raw if raw.startswith(("http://", "https://")) else None


def should_bypass_proxy(host: str, no_proxy: str | None) -> bool:
    if not no_proxy:
        return False
    entries = [entry.strip().lower() for entry in no_proxy.split(",") if entry.strip()]
    normalized_host = host.lower()
    for entry in entries:
        if entry == "*":
            return True
        trimmed = entry.lstrip(".")
        if normalized_host == trimmed or normalized_host.endswith(f".{trimmed}"):
            return True
    return False


def has_sufficient_depth_results(candidates: list[RawSearchCandidate]) -> bool:
    if not candidates:
        return False
    deep_results = sum(1 for candidate in candidates if not is_homepage_url(candidate.url))
    return deep_results >= max(1, len(candidates) // 2)


def is_homepage_url(url: str) -> bool:
    parts = urlsplit(url)
    path = (parts.path or "/").strip("/")
    return path == ""
