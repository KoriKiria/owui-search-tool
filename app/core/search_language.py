from __future__ import annotations

import re
from dataclasses import dataclass

LANGUAGE_PATTERN = re.compile(r"^[a-zA-Z]{2,3}(?:[-_][a-zA-Z]{2})?$")

DEFAULT_REGIONS = {
    "de": "DE",
    "en": "US",
    "es": "ES",
    "fr": "FR",
    "it": "IT",
    "nl": "NL",
    "pl": "PL",
    "pt": "BR",
    "uk": "UA",
}

LANGUAGE_ALIASES = {
    "auto": "auto",
    "english": "en",
    "german": "de",
    "polish": "pl",
}


@dataclass(frozen=True)
class SearchLanguage:
    raw: str
    code: str
    language: str
    region: str
    locale: str
    accept_language: str
    duckduckgo_kl: str


CHAR_HINTS = {
    "pl": set("ąćęłńóśżź"),
    "de": set("äöüß"),
    "fr": set("àâçéèêëîïôùûüÿœæ"),
    "es": set("áéíñóúü¿¡"),
}

SCRIPT_HINTS = {
    "ar": ((0x0600, 0x06FF),),
    "he": ((0x0590, 0x05FF),),
    "ja": ((0x3040, 0x30FF),),
    "ko": ((0xAC00, 0xD7AF),),
    "ru": ((0x0400, 0x04FF),),
    "uk": ((0x0400, 0x04FF),),
    "zh": ((0x4E00, 0x9FFF),),
}


def normalize_search_language(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("language must be a non-empty string")
    normalized = LANGUAGE_ALIASES.get(normalized.lower(), normalized)
    if normalized.lower() == "auto":
        return "auto"
    if not LANGUAGE_PATTERN.match(normalized):
        raise ValueError("language must be 'auto', a language code like 'pl', or a locale like 'pl-PL'")
    parts = normalized.replace("_", "-").split("-")
    if len(parts) == 1:
        return parts[0].lower()
    return f"{parts[0].lower()}-{parts[1].upper()}"


def resolve_search_language(value: str, default_locale: str) -> SearchLanguage:
    normalized = normalize_search_language(value)
    if normalized == "auto":
        normalized = normalize_search_language(default_locale)

    parts = normalized.split("-")
    language = parts[0]
    region = parts[1] if len(parts) == 2 else DEFAULT_REGIONS.get(language, language.upper())
    locale = f"{language}-{region}"
    accept_language = f"{language}-{region},{language};q=0.9"
    return SearchLanguage(
        raw=value,
        code=normalized,
        language=language,
        region=region,
        locale=locale,
        accept_language=accept_language,
        duckduckgo_kl=f"{language}-{region.lower()}",
    )


def resolve_search_language_for_query(value: str, default_locale: str, query: str | None) -> SearchLanguage:
    normalized = normalize_search_language(value)
    if normalized != "auto":
        return resolve_search_language(normalized, default_locale)

    inferred = detect_search_language(query or "")
    if inferred is not None:
        return resolve_search_language(inferred, default_locale)
    return resolve_search_language(default_locale, default_locale)


def detect_search_language(query: str) -> str | None:
    compact = query.strip().lower()
    if not compact:
        return None

    script_match = detect_script_language(compact)
    if script_match is not None:
        return script_match

    char_scores = {
        language: sum(1 for char in compact if char in charset)
        for language, charset in CHAR_HINTS.items()
    }
    char_winner = max(char_scores, key=char_scores.get)
    if char_scores[char_winner] > 0:
        return char_winner
    return None


def detect_script_language(text: str) -> str | None:
    counts = {
        language: sum(1 for char in text if any(start <= ord(char) <= end for start, end in ranges))
        for language, ranges in SCRIPT_HINTS.items()
    }
    winner = max(counts, key=counts.get)
    if counts[winner] > 0:
        return winner
    return None
