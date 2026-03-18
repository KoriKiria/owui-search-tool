# search-tool

OpenAPI tool server for Open WebUI that performs browser-backed web search plus page extraction in a single API workflow.

Search engine selection is configurable per request and by environment, with reliability-first defaults.

## Endpoints

- `POST /agent-search`
- `POST /extract-from-urls`
- `POST /fetch-content`
- `GET /healthz`
- `GET /readyz`
- `POST /health-check`
- `GET /openapi.json`

## Open WebUI

Import this server into Open WebUI as an OpenAPI tool server using the generated `openapi.json`.

## Run

```bash
docker compose up --build
```

## GitHub Actions

The repository workflow runs `pytest` and validates the Docker build on pushes, pull requests, and manual runs.

Manual Docker Hub publishing is available through GitHub Actions `workflow_dispatch` and pushes to `pentakilo/kilosearch`.

Required repository secret:

- `DOCKERHUB_TOKEN`: Docker Hub access token for the `pentakilo` account

Example with explicit file path from the repo root:

```bash
docker compose -f search-tool/docker-compose.yml up --build
```

Example with auth and proxy variables:

```bash
AUTH_ENABLED=true \
API_BEARER_TOKEN=secret \
HTTP_PROXY=http://proxy.example:3128 \
HTTPS_PROXY=http://proxy.example:3128 \
NO_PROXY=localhost,127.0.0.1,.internal.example \
docker compose -f search-tool/docker-compose.yml up --build
```

Example with optional search-provider credentials:

```bash
BING_API_KEY=... \
BRAVE_API_KEY=... \
GOOGLE_API_KEY=... \
GOOGLE_CSE_ID=... \
DUCKDUCKGO_API_KEY=... \
docker compose -f search-tool/docker-compose.yml up --build
```

Example `docker-compose.yml`:

```yaml
services:
  tool:
    image: pentakilo/kilosearch:latest
    environment:
      AUTH_ENABLED: "false"
      CORS_ALLOW_ORIGINS: "*"
      SEARCH_MAX_RESULTS: "8"
      SEARCH_ENGINE_DEFAULT: "auto"
      SEARCH_LANGUAGE_DEFAULT: "auto"
      SEARCH_TIMEOUT_MS: "20000"
      FETCH_TIMEOUT_MS: "8000"
      FETCH_MAX_CONCURRENCY: "4"
      FETCH_MAX_RESPONSE_BYTES: "500000"
      EXTRACT_MAX_CHARS: "4000"
      BLOCK_PRIVATE_NETWORKS: "true"
      BROWSER_ENABLED: "true"
      BROWSER_HEADLESS: "true"
      BROWSER_TIMEOUT_MS: "12000"
      HTTP_PROXY: "${HTTP_PROXY:-}"
      HTTPS_PROXY: "${HTTPS_PROXY:-}"
      NO_PROXY: "${NO_PROXY:-}"
      BING_API_KEY: "${BING_API_KEY:-}"
      BING_API_ENDPOINT: "${BING_API_ENDPOINT:-}"
      BRAVE_API_KEY: "${BRAVE_API_KEY:-}"
      BRAVE_API_ENDPOINT: "${BRAVE_API_ENDPOINT:-}"
      GOOGLE_API_KEY: "${GOOGLE_API_KEY:-}"
      GOOGLE_API_ENDPOINT: "${GOOGLE_API_ENDPOINT:-}"
      GOOGLE_CSE_ID: "${GOOGLE_CSE_ID:-}"
      DUCKDUCKGO_API_KEY: "${DUCKDUCKGO_API_KEY:-}"
      DUCKDUCKGO_API_ENDPOINT: "${DUCKDUCKGO_API_ENDPOINT:-}"
    ports:
      - "8100:8100"

  test-app:
    build:
      context: ./search-tool/test-app
      dockerfile: Dockerfile
    depends_on:
      - tool
    ports:
      - "8180:8080"
```

Default service URL:

- `http://192.168.10.200:8100`
- tester UI: `http://192.168.10.200:8180`

## Environment

- `AUTH_ENABLED`
- `API_BEARER_TOKEN`
- `CORS_ALLOW_ORIGINS`
- `SEARCH_MAX_RESULTS`
- `SEARCH_ENGINE_DEFAULT`
- `SEARCH_LANGUAGE_DEFAULT`
- `SEARCH_TIMEOUT_MS`
- `FETCH_TIMEOUT_MS`
- `FETCH_MAX_CONCURRENCY`
- `FETCH_MAX_RESPONSE_BYTES`
- `EXTRACT_MAX_CHARS`
- `BLOCK_PRIVATE_NETWORKS`
- `BROWSER_ENABLED`
- `BROWSER_HEADLESS`
- `BROWSER_TIMEOUT_MS`
- `HTTP_PROXY` / `http_proxy`
- `HTTPS_PROXY` / `https_proxy`
- `NO_PROXY` / `no_proxy`
- `BING_API_KEY`
- `BING_API_ENDPOINT`
- `BRAVE_API_KEY`
- `BRAVE_API_ENDPOINT`
- `GOOGLE_API_KEY`
- `GOOGLE_API_ENDPOINT`
- `GOOGLE_CSE_ID`
- `DUCKDUCKGO_API_KEY`
- `DUCKDUCKGO_API_ENDPOINT`

## Search Engine Selection

`POST /agent-search` accepts `search_engine`.

Supported values:

- `auto`
- `mixed`
- `all`
- `bing`
- `brave`
- `google`
- `duckduckgo`
- aliases: `ggg -> google`, `ddg -> duckduckgo`

Optional provider credentials:

- each supported engine can be configured with its own optional API key and optional API endpoint override
- `google` can also be configured with `GOOGLE_CSE_ID` for Custom Search Engine integrations
- the current implementation still uses Playwright/browser search as the primary path
- these credentials are accepted now so deployments can standardize secrets and add engine-specific API integrations without changing the public contract later

Recommended usage:

- `auto`: best default for reliability and availability
- `mixed`: Bing first, then best-effort fallback engines for more diversity
- `all`: tries every supported engine and merges results; slowest and least predictable
- `bing`: most reliable current engine in this implementation
- `google`, `brave`, `duckduckgo`: supported as explicit best-effort engines, but they may present anti-bot challenges depending on network reputation and deployment environment

Environment default:

```bash
SEARCH_ENGINE_DEFAULT=auto
```

## Language Selection

`POST /agent-search` also accepts `language`.

Examples:

- `auto`
- `pl`
- `en`
- `de`
- `pl-PL`
- `en-US`

Recommended usage:

- `language: "auto"`: only for cases where the query language is obvious from script or diacritics, otherwise it falls back to the server default
- `language: "pl"`: prefer Polish results
- `language: "en"`: prefer English results
- `language: "pl-PL"`: prefer Polish results specifically for Poland

Guidance for tool-calling LLMs:

- set `language` explicitly for non-English queries
- set `language` explicitly when the query is short, ambiguous, or language-sensitive
- do not rely on `auto` for Latin-script queries without clear language markers

This hint is passed into the browser locale, `Accept-Language`, and engine-specific locale parameters when supported.

## Test App

The repository includes a browser-based tester for the tool server.

It proxies requests through `/api` to avoid browser-to-container networking issues and lets you validate:

- `POST /agent-search`
- `POST /extract-from-urls`
- `POST /fetch-content`
- `GET /healthz`
- `GET /readyz`
- `POST /health-check`
- `GET /openapi.json`

## Tool Semantics

- `POST /agent-search`: `query` is a real web search query.
- `POST /extract-from-urls`: `focus_query` is an optional extraction hint for the provided URLs only. It does not trigger a new web search.
- `POST /fetch-content`: `focus_query` is an optional extraction hint for the fetched page only. It does not trigger a new web search.
