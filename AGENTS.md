# AGENTS.md

## Purpose

This repository implements an OpenAPI tool server for Open WebUI that provides Tavily-like, agent-oriented web research.

The primary workflow is a single API call that performs:

1. web search
2. candidate filtering
3. page retrieval
4. content extraction
5. relevance-oriented packaging

The integration target is Open WebUI's OpenAPI tool server model, not the simpler external web-search provider contract.

## Core rules

- Preserve the OpenAPI tool server integration model.
- Keep one primary high-value endpoint: `POST /agent-search`.
- Use Playwright for the search stage.
- Keep output optimized for agent consumption rather than UI rendering.
- Support bearer auth through environment variables.
- Support browser-safe CORS for Open WebUI user tool servers.
- Keep failure handling explicit and predictable.

## Required endpoints

- `POST /agent-search`
- `POST /extract-from-urls`
- `GET /healthz`
- `GET /readyz`
- `POST /health-check`

## Safety requirements

- Only allow `http` and `https` URLs.
- Block localhost and private-network targets by default.
- Cap page fetch count, fetch timeout, response size, and extracted content size.
- Close Playwright resources deterministically.

## Testing requirements

Add or maintain tests for:

- request validation
- auth failure
- no-results handling
- duplicate result collapse
- blocked URL rejection
- timeout behavior
- partial extraction failure
- health endpoints
