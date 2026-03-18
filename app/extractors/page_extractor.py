from __future__ import annotations

import ipaddress
import socket
from collections import OrderedDict
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from app.core.config import Settings
from app.core.errors import InvalidRequestError, UpstreamFailureError
from app.models import ExtractedPage


class PageExtractor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def extract(self, url: str, query: str | None, include_raw_content: bool) -> ExtractedPage:
        self._validate_target(url)
        timeout = httpx.Timeout(self._settings.fetch_timeout_ms / 1000)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            trust_env=True,
            headers={"User-Agent": self._settings.browser_user_agent},
        ) as client:
            response = await client.get(url)
        response.raise_for_status()

        if len(response.content) > self._settings.fetch_max_response_bytes:
            raise UpstreamFailureError("response exceeded maximum allowed size")

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
            tag.decompose()

        title = ""
        if soup.title and soup.title.string:
            title = " ".join(soup.title.string.split())
        text = extract_readable_text(soup)
        if not text:
            text = " ".join(soup.get_text(" ", strip=True).split())

        text = text[: self._settings.extract_max_chars]
        snippet = make_snippet(text, query)

        return ExtractedPage(
            url=url,
            title=title or url,
            content=text,
            snippet=snippet,
            raw_content=text if include_raw_content else None,
        )

    def _validate_target(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise InvalidRequestError("only absolute http/https URLs are allowed")
        if not self._settings.block_private_networks:
            return
        host = parts.hostname.lower()
        if host in {"localhost"} or host.endswith(".localhost"):
            raise InvalidRequestError("localhost targets are blocked")
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return
        for info in infos:
            address = info[4][0]
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise InvalidRequestError("private network targets are blocked")


def make_snippet(content: str, query: str | None) -> str:
    if not content:
        return ""
    if not query:
        return content[:280]
    lowered_query_terms = [term for term in query.lower().split() if len(term) > 2]
    for sentence in content.split("\n"):
        lowered = sentence.lower()
        if any(term in lowered for term in lowered_query_terms):
            return sentence[:280]
    return content[:280]


def extract_readable_text(soup: BeautifulSoup) -> str:
    containers = []
    for selector in ("article", "main", '[role="main"]', ".post", ".entry-content", ".article-content", ".recipe-content"):
        containers.extend(soup.select(selector))

    blocks = containers or soup.find_all(["p", "li", "h1", "h2", "h3"])
    ordered_parts: OrderedDict[str, None] = OrderedDict()
    for block in blocks:
        text = " ".join(block.get_text(" ", strip=True).split())
        if not is_useful_text(text):
            continue
        ordered_parts.setdefault(text, None)

    return "\n".join(list(ordered_parts.keys())[:40])


def is_useful_text(text: str) -> bool:
    if len(text) < 40:
        return False

    lowered = text.lower()
    junk_markers = (
        "zaloguj",
        "załóż konto",
        "ulubione przepisy",
        "na skróty",
        "see more",
        "więcej...",
        "cookies",
        "polityka prywatności",
        "regulamin",
        "newsletter",
    )
    if any(marker in lowered for marker in junk_markers):
        return False

    token_count = len(text.split())
    if token_count < 6:
        return False

    uppercase_ratio = sum(1 for char in text if char.isupper()) / max(1, sum(1 for char in text if char.isalpha()))
    if uppercase_ratio > 0.45:
        return False

    return True
