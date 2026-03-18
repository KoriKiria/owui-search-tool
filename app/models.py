from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.core.search_engines import normalize_search_engine
from app.core.search_language import normalize_search_language


class AgentSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    max_results: int = Field(default=5, gt=0, le=20)
    search_depth: Literal["fast", "basic", "advanced"] = "basic"
    topic: Literal["general", "news", "finance"] = "general"
    search_engine: str = "auto"
    language: str = Field(
        default="auto",
        description="Preferred search language or locale such as 'pl', 'en', 'de', or 'pl-PL'. Strongly recommended for non-English or language-sensitive queries. Use 'auto' only when the query language is obvious from script or diacritics; otherwise the caller should set this explicitly.",
    )
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    include_raw_content: bool = False
    extract_depth: Literal["summary", "full"] = "summary"

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must be a non-empty string")
        return stripped

    @field_validator("search_engine")
    @classmethod
    def validate_search_engine(cls, value: str) -> str:
        return normalize_search_engine(value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_search_language(value)


class ExtractFromUrlsRequest(BaseModel):
    urls: list[HttpUrl] = Field(min_length=1, max_length=20)
    focus_query: str | None = Field(
        default=None,
        description="Optional focus hint for extraction from the provided URLs. This does not perform a new web search.",
    )
    include_raw_content: bool = Field(
        default=False,
        description="Whether to include a less-processed version of the extracted page text.",
    )

    @field_validator("focus_query")
    @classmethod
    def validate_optional_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class FetchContentRequest(BaseModel):
    url: HttpUrl = Field(
        description="Absolute http or https URL of the exact web page to fetch and extract.",
    )
    focus_query: str | None = Field(
        default=None,
        description="Optional focus hint for extraction from this page only. This does not perform a new web search.",
    )
    include_raw_content: bool = Field(
        default=False,
        description="Whether to include a less-processed version of the extracted page text.",
    )

    @field_validator("focus_query")
    @classmethod
    def validate_fetch_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class RawSearchCandidate(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""
    engine: str = "unknown"


class SearchProviderResponse(BaseModel):
    candidates: list[RawSearchCandidate]
    engines_used: list[str]
    warnings: list[str]


class ExtractedPage(BaseModel):
    url: str
    title: str
    content: str
    snippet: str
    published_date: str | None = None
    source_type: str = "general"
    raw_content: str | None = None


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: HttpUrl
    content: str
    snippet: str
    score: float
    published_date: str | None = None
    source_type: str = "general"
    raw_content: str | None = None


class TimingBreakdown(BaseModel):
    total: int
    search: int
    fetch_extract: int


class AgentSearchResponse(BaseModel):
    query: str
    answer: str | None
    results: list[AgentResult]
    failed_urls: list[str]
    timing_ms: TimingBreakdown
    provider: str
    search_engine: str
    search_engines_used: list[str]
    language: str
    warnings: list[str]


class ExtractResponse(BaseModel):
    focus_query: str | None
    results: list[AgentResult]
    failed_urls: list[str]
    provider: str
    warnings: list[str]


class FetchContentResponse(BaseModel):
    focus_query: str | None
    result: AgentResult | None
    failed_url: str | None
    provider: str
    warnings: list[str]


class HealthResponse(BaseModel):
    status: str
    provider: str
    version: str
