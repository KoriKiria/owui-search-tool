
Below are two ready-to-use repository documents for an **Open WebUI OpenAPI tool server** that exposes a **single-call, Tavily-like agent search capability**. This design fits Open WebUI’s documented support for **OpenAPI servers as tools**, where Open WebUI ingests an OpenAPI spec and treats each endpoint as a callable tool. Open WebUI v0.6+ documents this integration path, and its external web-search docs separately confirm that the built-in external search setting is only for returning `{link,title,snippet}` search results, not full search+scrape+extract workflows. Tavily’s public docs describe the product pattern you want to emulate: search plus extraction-oriented workflows for AI agents. ([Open WebUI][1])

---

## `AGENTS.md`

````md
# AGENTS.md

## Purpose

This repository implements an **OpenAPI tool server for Open WebUI** that provides a Tavily-like, agent-optimized web research capability.

The server is not a plain "search API" in the narrow SERP sense. Its purpose is to give LLM agents a **single API call** that performs the following steps end-to-end:

1. web search
2. page retrieval / scraping
3. source filtering
4. content extraction
5. relevance selection
6. answer-oriented packaging of results

The implementation target is Open WebUI's documented **OpenAPI Tool Server** integration model, where Open WebUI imports an OpenAPI specification and exposes endpoints as callable tools to models and agents.

This repository must prioritize:
- reliable real-time information retrieval
- search behavior optimized for AI agents
- consolidated search + scrape + filter + extract workflows
- strong operational safety for large-scale web access
- simple integration into Open WebUI

---

## Product intent

Traditional search APIs often return generic ranked links that still require substantial post-processing. This system must instead behave like an **AI-native search tool**:

- optimized for LLM and agent workflows
- able to retrieve current online information
- able to scrape and extract relevant content
- able to filter weak or irrelevant sources
- able to return compact, useful, agent-ready output

The target user is:
- AI developers
- autonomous agents
- RAG pipelines
- research assistants
- Open WebUI tool users

---

## Ground rules

### Preserve the OpenAPI-server integration model
Open WebUI must be able to connect to this service using its documented OpenAPI server integration flow.

Do not redesign this into:
- a browser extension
- a custom Open WebUI fork
- an MCP-first implementation unless explicitly requested
- a provider tied only to Open WebUI web-search settings

This project is specifically an **OpenAPI tool server**.

### Prefer a single high-value endpoint
The main developer experience should center on one primary endpoint, such as:

- `POST /agent-search`

This endpoint should combine:
- search
- scraping
- filtering
- extraction
- packaging

Additional helper endpoints are acceptable, but the primary workflow must stay simple.

### Mimic Tavily's product behavior, not necessarily its exact wire format
The system should emulate Tavily's value proposition:
- one-call search + extract
- AI-ready results
- source filtering
- freshness-sensitive retrieval
- support for current web information

But it does not need to clone Tavily's exact API schema unless explicitly required.

---

## Required capabilities

The implementation must support:

1. **Real-time web search**
   - retrieve current online information
   - support newsy / recent queries
   - support general web discovery

2. **Web scraping**
   - fetch full page content from discovered URLs
   - support multiple pages per request
   - handle ordinary HTML pages robustly

3. **Filtering**
   - remove low-value or irrelevant pages
   - remove duplicate / near-duplicate results
   - reject obvious junk or unsupported pages

4. **Extraction**
   - extract the most relevant text from fetched pages
   - produce concise snippets, summaries, or extracted evidence
   - preserve URL attribution

5. **Agent-oriented output**
   - return results in a format directly useful to LLM tools
   - include enough structure for downstream reasoning
   - avoid forcing the model to parse noisy raw HTML

6. **Reliability**
   - bounded timeouts
   - partial success handling
   - robust failure reporting
   - graceful degradation when some URLs fail

---

## Recommended architecture

Prefer this layered design:

- API layer
  - FastAPI
  - OpenAPI schema generation
  - auth
  - request validation
  - structured error responses

- Orchestration layer
  - query handling
  - search planning
  - per-request budget allocation
  - result merging
  - extraction packaging

- Search layer
  - web search backend(s)
  - optional provider abstraction
  - freshness-aware ranking

- Fetching / scraping layer
  - HTTP fetching
  - HTML parsing
  - content sanitization
  - retry / timeout policy

- Extraction layer
  - page text extraction
  - relevance scoring
  - answer-oriented condensation

- Infra layer
  - logging
  - metrics
  - rate limiting
  - config
  - caching

---

## Suggested implementation stack

Preferred defaults:
- Python 3.11+
- FastAPI
- Pydantic
- httpx
- BeautifulSoup or readability-style extraction
- lxml
- tenacity for retries
- pytest
- ruff
- mypy

Optional:
- Playwright for JS-heavy fallback fetching
- Redis for caching / rate limiting
- OpenTelemetry

Alternative stacks are acceptable if they preserve maintainability and OpenAPI quality.

---

## Primary API shape

The main endpoint should be designed for a single-call agent workflow.

Recommended request model:

```json
{
  "query": "latest policy on xyz",
  "max_results": 8,
  "search_depth": "basic",
  "topic": "general",
  "include_domains": ["example.com"],
  "exclude_domains": ["spam.example"],
  "include_raw_content": false,
  "extract_depth": "summary"
}
````

Recommended response model:

```json
{
  "query": "latest policy on xyz",
  "answer": "Optional compact synthesized answer or extracted overview",
  "results": [
    {
      "title": "Example Title",
      "url": "https://example.com/article",
      "content": "Condensed extracted content",
      "snippet": "Short relevance snippet",
      "score": 0.92,
      "published_date": "2026-03-10",
      "source_type": "news"
    }
  ],
  "failed_urls": [],
  "timing_ms": {
    "total": 1840,
    "search": 220,
    "fetch_extract": 1510
  }
}
```

Do not expose excessive internal complexity in the public API unless necessary.

---

## OpenAPI requirements

The OpenAPI spec must be:

* valid OpenAPI 3.0+ or 3.1
* human-readable
* stable
* explicit about auth
* explicit about error responses
* explicit about rate limits and timeouts where relevant

Every public endpoint must include:

* summary
* description
* request schema
* response schema
* error schema
* examples

The generated `/openapi.json` must be suitable for direct import into Open WebUI.

---

## Authentication

The service should support bearer-token authentication.

Preferred behavior:

* `Authorization: Bearer <token>`
* configurable through environment variable
* reject unauthorized requests with `401`

Do not:

* log tokens
* accept auth in query parameters
* expose unauthenticated admin endpoints in production

---

## Search quality requirements

The system must optimize for **answer relevance**, not just document listing.

Agents working on this code should prefer:

* direct relevance to the user query
* recent / current information where appropriate
* diverse but credible sources
* deduplication
* short agent-usable extracted text

Agents should avoid:

* shallow link dumps
* excessive source count with little value
* spammy or templated pages
* raw page boilerplate in final results

---

## Scraping and extraction rules

The implementation must:

* fetch candidate pages discovered in search
* extract readable text
* strip navigation boilerplate where possible
* preserve source attribution
* filter very low-information pages
* truncate oversized extracted text to configured limits

If JS-heavy fallback is implemented:

* isolate browser contexts
* enforce strict timeouts
* close browser resources deterministically

---

## Reliability expectations

The system must:

* support partial success
* return useful results even if some pages fail
* avoid crashing on malformed HTML
* set request-scoped timeout budgets
* bound concurrency
* degrade gracefully

Preferred behavior:

* total request timeout configurable
* per-page timeout configurable
* per-domain concurrency configurable
* duplicate URL collapse
* retry only transient failures

---

## Safety and security

This service performs outbound web access, so agents must protect against:

* SSRF
* local-network targeting
* cloud metadata endpoint access
* unbounded redirects
* dangerous URL schemes
* decompression bombs or oversized payloads
* hostile HTML causing resource exhaustion

Minimum safeguards:

* allow only http/https
* reject localhost and private-network destinations by default
* cap response sizes
* cap redirect chains
* cap pages fetched per request
* cap max extracted characters

If domain allowlisting is requested, implement it centrally.

---

## Performance and scale

The system should support large-scale scraping workloads, but agents must optimize in this order:

1. correctness
2. safety
3. reliability
4. latency
5. cost

Recommended defaults:

* fetch top N candidate pages only
* cache recent search/fetch results where appropriate
* keep extraction lightweight by default
* allow deeper extraction only via explicit parameters

---

## Observability

Use structured logging.

Each request should record:

* request_id
* normalized query hash
* requested parameters
* search backend used
* candidate URL count
* fetched URL count
* final result count
* timeout/failure counters
* latency breakdown

Metrics should include:

* request volume
* success/failure counts
* timeout counts
* average fetched pages per request
* extraction failure counts
* cache hit rate

---

## Tests required

Every meaningful change must preserve or improve:

* request validation tests
* auth tests
* search orchestration tests
* extraction tests
* duplicate filtering tests
* timeout tests
* partial-success tests
* OpenAPI schema smoke tests

Add tests for:

* blank query
* invalid max_results
* auth failure
* no results
* duplicate URLs
* page fetch timeout
* malformed HTML
* oversized page rejection
* blocked private-network URL
* partial success response
* OpenAPI schema generation

---

## Suggested repo layout

* `app/main.py`
* `app/api/routes.py`
* `app/models.py`
* `app/core/config.py`
* `app/core/security.py`
* `app/core/logging.py`
* `app/services/agent_search.py`
* `app/services/search_backend.py`
* `app/services/fetcher.py`
* `app/services/extractor.py`
* `app/services/filtering.py`
* `app/services/ranking.py`
* `tests/`
* `README.md`
* `SPEC.md`
* `AGENTS.md`

---

## Workflow for coding agents

When working on this repository:

1. Read `SPEC.md` first.
2. Preserve the public API unless the spec is explicitly updated.
3. Keep the primary endpoint simple and high-value.
4. Prefer additive improvements over large rewrites.
5. Add or update tests with every behavioral change.
6. Verify OpenAPI correctness before finishing.
7. Summarize tradeoffs and unresolved risks in the handoff.

---

## Safe-change policy

Agents may safely change:

* internal architecture
* ranking heuristics
* extraction internals
* retry policies
* caching internals
* logging and metrics
* test coverage

Agents must not silently change:

* public endpoint names
* auth semantics
* public request/response schema
* security posture
* timeout model
* OpenAPI importability

These require corresponding `SPEC.md` updates.

---

## Definition of done

A task is done only when:

* the server runs
* `/openapi.json` is valid
* Open WebUI can import the server as an OpenAPI tool server
* the main endpoint performs search + scrape + filter + extract in one call
* auth works
* tests pass
* docs are accurate
* obvious SSRF and resource-abuse risks are addressed

````

---

## `SPEC.md`

```md
# SPEC.md

# Agent Search OpenAPI Server for Open WebUI
Version: 0.1.0
Status: Draft

## 1. Overview

This project defines an OpenAPI tool server intended for integration with Open WebUI.

The service provides a Tavily-like, AI-native web research capability through a single API call that combines:

- web search
- web page retrieval
- content scraping
- filtering irrelevant sources
- extraction of relevant information
- packaging of agent-ready output

The purpose is to overcome limitations of traditional search APIs that often return only ranked links or loosely related articles. This service is designed for AI agents, LLM applications, and developer workflows that need current web information with minimal orchestration burden.

The primary integration target is Open WebUI's documented OpenAPI tool server support.

---

## 2. Goals

### Primary goals
- Provide an OpenAPI server importable into Open WebUI.
- Offer a single endpoint for agent-oriented search and extraction.
- Retrieve real-time web information.
- Support scalable web fetching and extraction.
- Filter irrelevant sources automatically.
- Return structured, high-value results suitable for LLM consumption.
- Be fast, persistent, and reliable for AI workflows.

### Non-goals
- Full browser automation platform
- Generic site crawler as a primary interface
- Human-facing search portal
- Open WebUI external web-search-provider replacement
- Exact clone of Tavily's proprietary internals

---

## 3. Integration model

### 3.1 Open WebUI integration target
This service is designed to be connected to Open WebUI as an **OpenAPI server / tool server**.

Open WebUI should ingest the service's OpenAPI definition and expose its endpoints as callable tools to models and agents.

### 3.2 Distinction from Open WebUI external search provider
This project is not limited to Open WebUI's built-in "External Web Search URL" contract.

That built-in external web-search setting is documented for returning a list of search results. This project instead provides a richer tool endpoint that performs search plus scraping plus extraction in one API call.

---

## 4. Functional requirements

The system must:

1. integrate a search capability designed for tasks requiring real-time online information retrieval
2. support large-scale web scraping
3. provide customizable search behavior suitable for AI agents and LLM applications
4. automatically perform the following within a single API request:
   - web searching
   - content scraping
   - filtering irrelevant sources
   - extracting the most relevant information
5. return fast, persistent, and reliable results
6. mimic the product behavior associated with AI-native search systems such as Tavily

---

## 5. Public API

## 5.1 Primary endpoint

### `POST /agent-search`

This is the primary endpoint for single-call AI-native search.

### Purpose
Execute search, fetch, filtering, and extraction in one request.

### Authentication
Optional but recommended:
- `Authorization: Bearer <token>`

### Request body schema

```json
{
  "query": "latest developments in battery recycling policy",
  "max_results": 8,
  "search_depth": "basic",
  "topic": "general",
  "days": 30,
  "include_domains": ["reuters.com", "iea.org"],
  "exclude_domains": ["pinterest.com"],
  "include_answer": true,
  "include_raw_content": false,
  "include_images": false,
  "extract_depth": "summary"
}
````

### Request fields

#### `query`

* type: string
* required: yes
* constraints:

  * non-empty after trimming

#### `max_results`

* type: integer
* required: no
* default: 5
* constraints:

  * minimum 1
  * maximum configurable, suggested hard cap 20

#### `search_depth`

* type: string enum
* values:

  * `basic`
  * `advanced`
* default: `basic`

Semantics:

* `basic`: prioritize speed and bounded fetch scope
* `advanced`: allow broader search and deeper retrieval within limits

#### `topic`

* type: string enum
* values:

  * `general`
  * `news`
  * `finance`
* default: `general`

#### `days`

* type: integer
* required: no
* meaning:

  * freshness window in days where relevant
* constraints:

  * minimum 1
  * maximum configurable

#### `include_domains`

* type: array of strings
* required: no
* meaning:

  * preferred or allowed source domains

#### `exclude_domains`

* type: array of strings
* required: no
* meaning:

  * blocked domains for this request

#### `include_answer`

* type: boolean
* default: true
* meaning:

  * whether to return a compact synthesized or extracted overview

#### `include_raw_content`

* type: boolean
* default: false
* meaning:

  * whether to include larger extracted page text segments

#### `include_images`

* type: boolean
* default: false
* meaning:

  * reserved for future support; optional in MVP

#### `extract_depth`

* type: string enum
* values:

  * `snippet`
  * `summary`
  * `detailed`
* default: `summary`

---

## 5.2 Success response

HTTP `200 OK`

```json
{
  "query": "latest developments in battery recycling policy",
  "answer": "Recent policy developments emphasize producer responsibility, recycling targets, and supply chain transparency.",
  "results": [
    {
      "title": "EU updates battery regulation guidance",
      "url": "https://example.com/eu-battery-guidance",
      "content": "The updated guidance clarifies compliance timelines and recycling obligations for producers...",
      "snippet": "Updated guidance on compliance timelines and recycling obligations.",
      "score": 0.93,
      "published_date": "2026-03-11",
      "source_type": "news",
      "domain": "example.com"
    }
  ],
  "failed_urls": [],
  "timing_ms": {
    "total": 1820,
    "search": 210,
    "fetch_extract": 1470,
    "ranking": 140
  }
}
```

### Response fields

#### `query`

* echoed normalized query string

#### `answer`

* optional compact synthesized or extracted overview
* must be concise
* may be omitted if `include_answer=false`

#### `results`

* array of result objects
* ordered by descending relevance

#### `failed_urls`

* array of URLs that could not be fetched or processed
* may be empty

#### `timing_ms`

* optional diagnostic object
* useful for developers and observability

---

## 5.3 Result object schema

Each `results[]` item should contain:

### `title`

* type: string
* required: yes

### `url`

* type: string
* required: yes
* must be absolute `http` or `https`

### `content`

* type: string
* required: recommended
* extracted and condensed page text
* length bounded by config

### `snippet`

* type: string
* required: yes
* concise relevance-oriented summary

### `score`

* type: number
* required: optional but recommended
* normalized relevance score, suggested range 0 to 1

### `published_date`

* type: string
* optional
* ISO 8601 date or datetime when available

### `source_type`

* type: string
* optional
* example values:

  * `news`
  * `blog`
  * `documentation`
  * `government`
  * `academic`

### `domain`

* type: string
* optional

---

## 5.4 Health endpoints

### `GET /healthz`

Liveness endpoint.

Success:

```json
{
  "status": "ok"
}
```

### `GET /readyz`

Readiness endpoint.

Success:

```json
{
  "status": "ready"
}
```

The readiness check may verify:

* config loaded
* search backend available
* cache reachable if required
* optional browser runtime readiness if enabled

---

## 6. Internal processing model

Each `/agent-search` request should execute the following pipeline:

1. validate request
2. normalize query
3. select search strategy
4. perform web search
5. deduplicate candidate URLs
6. fetch candidate pages
7. extract readable content
8. filter irrelevant or low-value sources
9. score and rank extracted results
10. optionally produce compact answer text
11. return structured response

This should occur within one client request.

---

## 7. Search behavior requirements

The system must optimize for AI-agent usefulness, not only for keyword ranking.

It should:

* favor directly relevant sources
* prefer high-information pages
* preserve freshness where relevant
* handle recency-sensitive queries
* support domain include/exclude controls
* support bounded deeper search in advanced mode

It must avoid:

* returning only raw SERP-style lists
* sending back boilerplate-heavy content
* over-fetching beyond configured limits
* filling results with weakly related pages

---

## 8. Scraping and extraction requirements

The system must:

* fetch the content of discovered pages
* extract readable text from HTML
* remove or reduce navigation boilerplate
* preserve page attribution
* support concurrent fetching within limits
* bound content size
* handle malformed HTML robustly

Optional JS-heavy support:

* a fallback headless browser path may be enabled for selected pages
* this must be off by default unless explicitly configured
* browser use must remain strongly bounded

---

## 9. Filtering and ranking requirements

The system must implement filtering of irrelevant sources.

At minimum it should:

* remove exact duplicate URLs
* remove near-duplicate content where practical
* reject very thin pages
* reject unsupported schemes or unsafe URLs
* score results based on query relevance and source quality

Ranking signals may include:

* textual relevance
* domain quality
* freshness
* extraction completeness
* content density
* title/query alignment

---

## 10. Reliability requirements

The system must:

* support partial success
* continue when some candidate pages fail
* expose failed URL information
* enforce total request timeouts
* enforce per-fetch timeouts
* cap pages fetched per request
* cap concurrency
* cap extraction size

Recommended defaults:

* default `max_results=5`
* candidate fetch cap 8 to 12
* per-page timeout 5 to 10 seconds
* total request timeout 10 to 20 seconds

---

## 11. Security requirements

Because the service fetches arbitrary public URLs, it must defend against abuse.

The implementation must:

* allow only `http` and `https`
* reject localhost and private-network targets by default
* reject cloud metadata IP ranges by default
* cap redirects
* cap response size
* cap decompressed body size
* reject dangerous MIME types where relevant
* reject unsupported URL schemes
* support bearer-token auth in production

The implementation should:

* support domain allowlists
* support deny lists
* support outbound proxy configuration
* redact sensitive values from logs

---

## 12. Non-functional requirements

## 12.1 Performance

The system should be fast enough for interactive agent use.

Suggested targets:

* P50 under 3 seconds for basic mode with lightweight pages
* P95 under 10 seconds for advanced mode under normal conditions

## 12.2 Persistence

The system should support persistent reliability through:

* configurable caching
* retry policies for transient failures
* consistent request and error handling
* stable response schema

## 12.3 Observability

The service should emit:

* structured logs
* latency metrics
* fetch counts
* timeout counts
* extraction failure counts
* cache metrics if used

---

## 13. Error handling

### `400 Bad Request`

Invalid request payload.

Example:

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "query must be a non-empty string"
  }
}
```

### `401 Unauthorized`

Missing or invalid bearer token.

Example:

```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "invalid bearer token"
  }
}
```

### `429 Too Many Requests`

Request rate exceeded.

Example:

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "too many requests"
  }
}
```

### `502 Bad Gateway` or `503 Service Unavailable`

Search backend or fetch pipeline unavailable.

Example:

```json
{
  "error": {
    "code": "UPSTREAM_FAILURE",
    "message": "search or fetch backend unavailable"
  }
}
```

### `500 Internal Server Error`

Unexpected internal failure.

Example:

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "unexpected server error"
  }
}
```

Partial-success cases should still return `200 OK` when meaningful results are available.

---

## 14. Configuration

Recommended environment variables:

* `APP_HOST`
* `APP_PORT`
* `LOG_LEVEL`
* `AUTH_ENABLED`
* `API_BEARER_TOKEN`
* `SEARCH_BACKEND`
* `SEARCH_TIMEOUT_MS`
* `FETCH_TIMEOUT_MS`
* `TOTAL_REQUEST_TIMEOUT_MS`
* `MAX_RESULTS_DEFAULT`
* `MAX_RESULTS_HARD_CAP`
* `MAX_FETCHED_PAGES`
* `MAX_REDIRECTS`
* `MAX_RESPONSE_BYTES`
* `MAX_EXTRACTED_CHARS`
* `ALLOW_PRIVATE_NET=false`
* `BLOCK_LOCALHOST=true`
* `CACHE_ENABLED`
* `CACHE_TTL_SECONDS`
* `JS_FALLBACK_ENABLED`
* `JS_FALLBACK_TIMEOUT_MS`

---

## 15. Suggested internal architecture

```text
Client (Open WebUI Tool Call)
        |
        v
   POST /agent-search
        |
        v
API Layer (FastAPI / OpenAPI)
        |
        v
Orchestrator
   |      |       |        |
   v      v       v        v
Search  Fetch   Extract   Filter/Rank
   \      |       |        /
    \     |       |       /
     \    +-------+------/
      \          |
       \         v
        +--> Response Builder
                |
                v
           Agent-ready JSON
```

---

## 16. OpenAPI requirements

The implementation must generate an OpenAPI document that:

* is valid OpenAPI 3.x
* clearly defines auth
* documents all request fields
* documents all response schemas
* provides examples
* is directly consumable by Open WebUI

The OpenAPI title should clearly indicate:

* this is an agent-search tool server
* it performs search + scrape + extract

Suggested title:
`Agent Search Tool Server`

---

## 17. Testing requirements

### Unit tests

* request validation
* query normalization
* URL safety checks
* filtering
* extraction truncation
* ranking behavior
* auth checks

### Integration tests

* successful `/agent-search`
* blank query
* invalid `max_results`
* auth failure
* no results
* partial success
* readiness and health endpoints
* OpenAPI schema generation

### Resilience tests

* per-page timeout
* malformed HTML
* oversized response body
* blocked private IP target
* duplicate URL collapse
* degraded backend behavior

---

## 18. Acceptance criteria

The implementation is acceptable when:

1. Open WebUI can import the server as an OpenAPI tool server.
2. The primary endpoint performs search + scrape + filter + extract in one call.
3. The response is structured and useful to an LLM.
4. The service supports current web information retrieval.
5. Partial success works without request failure.
6. Auth and basic abuse controls are implemented.
7. The OpenAPI spec is valid.
8. Tests cover the main workflows and failure modes.
9. Docs match implementation behavior.

---

## 19. Future extensions

Possible later additions:

* dedicated `/extract`
* dedicated `/crawl`
* domain-scoped research mode
* evidence spans / quoted passages
* citation confidence scores
* recency controls by source type
* per-tenant API keys
* streaming progress
* async job mode for very deep research

These must remain compatible with the core OpenAPI-tool-server model.

```

These requirements align with Open WebUI’s documented OpenAPI server integration path, and they intentionally distinguish this tool-server approach from the narrower built-in external web-search provider setting. Tavily’s docs also support the product rationale for combining search and extraction-oriented workflows for AI applications. :contentReference[oaicite:1]{index=1}

I can also turn these into a concrete `openapi.yaml` and a FastAPI project skeleton.
::contentReference[oaicite:2]{index=2}
```

[1]: https://docs.openwebui.com/features/extensibility/plugin/tools/openapi-servers/?utm_source=chatgpt.com "OpenAPI Tool Servers | Open WebUI"

