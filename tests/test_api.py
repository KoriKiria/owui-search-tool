import asyncio

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_research_service
from app.main import create_app
from app.models import (
    AgentResult,
    AgentSearchRequest,
    AgentSearchResponse,
    ExtractFromUrlsRequest,
    ExtractResponse,
    FetchContentRequest,
    FetchContentResponse,
    TimingBreakdown,
)


class StubResearchService:
    def __init__(
        self,
        agent_response: AgentSearchResponse | None = None,
        extract_response: ExtractResponse | None = None,
        fetch_response: FetchContentResponse | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._agent_response = agent_response
        self._extract_response = extract_response
        self._fetch_response = fetch_response
        self._exc = exc

    async def agent_search(self, payload: AgentSearchRequest, request_id: str) -> AgentSearchResponse:
        if self._exc:
            raise self._exc
        assert request_id
        return self._agent_response or AgentSearchResponse(
            query=payload.query,
            answer=None,
            results=[],
            failed_urls=[],
            timing_ms=TimingBreakdown(total=1, search=1, fetch_extract=0),
            provider="stub",
            search_engine=payload.search_engine,
            search_engines_used=["bing"] if payload.search_engine in {"auto", "mixed", "all"} else [payload.search_engine],
            language=payload.language,
            warnings=[],
        )

    async def extract_from_urls(self, payload: ExtractFromUrlsRequest, request_id: str) -> ExtractResponse:
        if self._exc:
            raise self._exc
        assert request_id
        return self._extract_response or ExtractResponse(
            focus_query=payload.focus_query,
            results=[],
            failed_urls=[],
            provider="stub",
            warnings=[],
        )

    async def fetch_content(self, payload: FetchContentRequest, request_id: str) -> FetchContentResponse:
        if self._exc:
            raise self._exc
        assert request_id
        return self._fetch_response or FetchContentResponse(
            focus_query=payload.focus_query,
            result=None,
            failed_url=str(payload.url),
            provider="stub",
            warnings=["fetch failed"],
        )


def make_client(service: StubResearchService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_research_service] = lambda: service
    return TestClient(app)


def test_health_endpoints(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    assert client.post("/health-check").status_code == 200


def test_agent_search_success() -> None:
    service = StubResearchService(
        agent_response=AgentSearchResponse(
            query="open webui",
            answer="summary",
            results=[
                AgentResult(
                    title="Open WebUI",
                    url="https://docs.openwebui.com/",
                    content="platform",
                    snippet="platform",
                    score=1.0,
                )
            ],
            failed_urls=[],
            timing_ms=TimingBreakdown(total=10, search=2, fetch_extract=8),
            provider="stub",
            search_engine="auto",
            search_engines_used=["bing"],
            language="en",
            warnings=[],
        )
    )
    client = make_client(service)

    response = client.post("/agent-search", json={"query": "open webui", "max_results": 3, "language": "en"})

    assert response.status_code == 200
    assert response.json()["results"][0]["url"] == "https://docs.openwebui.com/"
    assert response.json()["language"] == "en"


def test_extract_from_urls_success() -> None:
    service = StubResearchService(
        extract_response=ExtractResponse(
            focus_query="open webui",
            results=[
                AgentResult(
                    title="Open WebUI",
                    url="https://docs.openwebui.com/",
                    content="platform",
                    snippet="platform",
                    score=0.8,
                )
            ],
            failed_urls=[],
            provider="stub",
            warnings=[],
        )
    )
    client = make_client(service)

    response = client.post(
        "/extract-from-urls",
        json={"urls": ["https://docs.openwebui.com/"], "focus_query": "open webui"},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["title"] == "Open WebUI"


def test_fetch_content_success() -> None:
    service = StubResearchService(
        fetch_response=FetchContentResponse(
            focus_query="open webui",
            result=AgentResult(
                title="Open WebUI",
                url="https://docs.openwebui.com/",
                content="platform",
                snippet="platform",
                score=0.9,
            ),
            failed_url=None,
            provider="stub",
            warnings=[],
        )
    )
    client = make_client(service)

    response = client.post(
        "/fetch-content",
        json={"url": "https://docs.openwebui.com/", "focus_query": "open webui"},
    )

    assert response.status_code == 200
    assert response.json()["result"]["url"] == "https://docs.openwebui.com/"


def test_invalid_query_returns_400(client: TestClient) -> None:
    response = client.post("/agent-search", json={"query": "   ", "max_results": 1})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_invalid_urls_payload_returns_400(client: TestClient) -> None:
    response = client.post("/extract-from-urls", json={"urls": []})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_invalid_fetch_payload_returns_400(client: TestClient) -> None:
    response = client.post("/fetch-content", json={"url": "notaurl"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_auth_failure_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("API_BEARER_TOKEN", "secret")
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/agent-search", json={"query": "test"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_no_results_response() -> None:
    client = make_client(StubResearchService())
    response = client.post("/agent-search", json={"query": "nothing", "max_results": 3})
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_service_exception_returns_500() -> None:
    client = make_client(StubResearchService(exc=RuntimeError("boom")))
    response = client.post("/agent-search", json={"query": "open webui"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_timeout_shape_with_empty_results() -> None:
    class SlowService(StubResearchService):
        async def agent_search(self, payload: AgentSearchRequest, request_id: str) -> AgentSearchResponse:
            await asyncio.sleep(0.01)
            return await super().agent_search(payload, request_id)

    client = make_client(SlowService())
    response = client.post("/agent-search", json={"query": "open webui"})
    assert response.status_code == 200
    assert "timing_ms" in response.json()


def test_search_engine_alias_is_normalized() -> None:
    client = make_client(StubResearchService())
    response = client.post("/agent-search", json={"query": "open webui", "search_engine": "ggg"})
    assert response.status_code == 200


def test_invalid_search_engine_returns_400(client: TestClient) -> None:
    response = client.post("/agent-search", json={"query": "open webui", "search_engine": "askjeeves"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_language_is_accepted() -> None:
    client = make_client(StubResearchService())
    response = client.post("/agent-search", json={"query": "open webui", "language": "pl"})
    assert response.status_code == 200
    assert response.json()["language"] == "pl"


def test_invalid_language_returns_400(client: TestClient) -> None:
    response = client.post("/agent-search", json={"query": "open webui", "language": "polish-poland-extra"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
