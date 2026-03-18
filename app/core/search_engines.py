from __future__ import annotations

SUPPORTED_SEARCH_ENGINES = {
    "auto",
    "mixed",
    "all",
    "bing",
    "brave",
    "google",
    "duckduckgo",
}

SEARCH_ENGINE_ALIASES = {
    "ddg": "duckduckgo",
    "duck": "duckduckgo",
    "ggg": "google",
}

AUTO_ENGINE_ORDER = ["bing", "brave", "duckduckgo", "google"]
MIXED_ENGINE_ORDER = ["bing", "brave", "duckduckgo"]
ALL_ENGINE_ORDER = ["bing", "brave", "duckduckgo", "google"]


def normalize_search_engine(value: str) -> str:
    normalized = value.strip().lower()
    normalized = SEARCH_ENGINE_ALIASES.get(normalized, normalized)
    if normalized not in SUPPORTED_SEARCH_ENGINES:
        raise ValueError(
            "search_engine must be one of: auto, mixed, all, bing, brave, google, duckduckgo"
        )
    return normalized


def resolve_engine_plan(engine: str) -> list[str]:
    normalized = normalize_search_engine(engine)
    if normalized == "auto":
        return AUTO_ENGINE_ORDER.copy()
    if normalized == "mixed":
        return MIXED_ENGINE_ORDER.copy()
    if normalized == "all":
        return ALL_ENGINE_ORDER.copy()
    return [normalized]


def should_stop_after_success(engine: str, unique_count: int, requested_count: int, has_sufficient_depth: bool) -> bool:
    normalized = normalize_search_engine(engine)
    if normalized in {"auto", "bing", "brave", "google", "duckduckgo"}:
        if normalized == "auto":
            return unique_count >= requested_count and has_sufficient_depth
        return unique_count >= requested_count
    if normalized == "mixed":
        return unique_count >= max(requested_count, requested_count * 2) and has_sufficient_depth
    if normalized == "all":
        return False
    return True
