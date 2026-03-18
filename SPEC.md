# SPEC.md

# Real-Time Web Research Tool Server for Open WebUI
Version: 0.1.0
Status: Draft

## 1. Purpose

This project provides an OpenAPI-compatible tool server for Open WebUI that delivers real-time web research for AI agents and LLM workflows.

The server exposes tool endpoints that Open WebUI can import as an external OpenAPI tool server. The public contract is agent-oriented and designed for one-call search plus extraction workflows.

## 2. Primary operations

### `POST /agent-search`

Input:

```json
{
  "query": "latest policy on xyz",
  "max_results": 5,
  "language": "en",
  "search_depth": "basic",
  "topic": "general",
  "include_domains": ["example.com"],
  "exclude_domains": ["spam.example"],
  "include_raw_content": false,
  "extract_depth": "summary"
}
```

Response:

```json
{
  "query": "latest policy on xyz",
  "answer": "Optional synthesized answer",
  "results": [
    {
      "title": "Example Title",
      "url": "https://example.com/article",
      "content": "Condensed extracted content",
      "snippet": "Short relevance snippet",
      "score": 0.92,
      "published_date": null,
      "source_type": "general",
      "raw_content": null
    }
  ],
  "failed_urls": [],
  "timing_ms": {
    "total": 1200,
    "search": 300,
    "fetch_extract": 850
  },
  "provider": "playwright-bing",
  "language": "en",
  "warnings": []
}
```

### `POST /extract-from-urls`

Input:

```json
{
  "urls": ["https://example.com/article"],
  "focus_query": "optional extraction hint for these pages",
  "include_raw_content": false
}
```

Response:

- extracted content per URL
- failed URL list
- provider metadata
- `focus_query` only guides extraction from the provided URLs and does not trigger a new search

### `POST /fetch-content`

Input:

```json
{
  "url": "https://example.com/article",
  "focus_query": "optional extraction hint for this page",
  "include_raw_content": false
}
```

Response:

- extracted content for a single URL
- failed URL field when fetching fails
- provider metadata
- `focus_query` only guides extraction from the fetched page and does not trigger a new search

### Health endpoints

- `GET /healthz`
- `GET /readyz`
- `POST /health-check`

## 3. Functional requirements

- Search must use a real browser-backed provider.
- The service should accept optional per-engine API credentials for supported search providers so deployments can supply provider-specific secrets without changing the API contract.
- Search should allow the caller to set a preferred language or locale per request.
- Tool-calling clients should set `language` explicitly for non-English or ambiguous Latin-script queries instead of relying on automatic detection.
- Candidate pages must be fetched and converted into readable text.
- Duplicate URLs must be removed.
- Include/exclude domain filters must be applied.
- Partial failures must not fail the whole request unless all retrieval fails.
- Auth must support `Authorization: Bearer <token>` when enabled.
- CORS must be configurable for Open WebUI browser-side tool calls.

Recommended optional provider credential environment variables:

- `BING_API_KEY`
- `BING_API_ENDPOINT`
- `BRAVE_API_KEY`
- `BRAVE_API_ENDPOINT`
- `GOOGLE_API_KEY`
- `GOOGLE_API_ENDPOINT`
- `GOOGLE_CSE_ID`
- `DUCKDUCKGO_API_KEY`
- `DUCKDUCKGO_API_ENDPOINT`

## 4. Safety requirements

- Only `http` and `https` URLs are allowed.
- Localhost and private network targets are blocked by default.
- Oversized responses are truncated.
- Page fetch count and per-request timeout budgets are bounded.

## 5. Error model

Error responses use:

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "query must be a non-empty string"
  }
}
```

Codes:

- `INVALID_REQUEST`
- `UNAUTHORIZED`
- `UPSTREAM_FAILURE`
- `INTERNAL_ERROR`
