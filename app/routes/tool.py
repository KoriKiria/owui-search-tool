from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.auth import require_bearer_token
from app.dependencies import get_research_service
from app.models import AgentSearchRequest, ExtractFromUrlsRequest, FetchContentRequest, HealthResponse
from app.services.research_service import ResearchService

router = APIRouter()


@router.post(
    "/agent-search",
    response_model_exclude_none=True,
    dependencies=[Depends(require_bearer_token)],
    summary="Agent-oriented web search and extraction",
)
async def agent_search(
    payload: AgentSearchRequest,
    service: ResearchService = Depends(get_research_service),
):
    return await service.agent_search(payload, request_id=str(uuid4()))


@router.post(
    "/extract-from-urls",
    response_model_exclude_none=True,
    dependencies=[Depends(require_bearer_token)],
    summary="Extract content from known URLs using an optional focus query",
)
async def extract_from_urls(
    payload: ExtractFromUrlsRequest,
    service: ResearchService = Depends(get_research_service),
):
    return await service.extract_from_urls(payload, request_id=str(uuid4()))


@router.post(
    "/fetch-content",
    response_model_exclude_none=True,
    dependencies=[Depends(require_bearer_token)],
    summary="Fetch and extract content from one known URL using an optional focus query",
)
async def fetch_content(
    payload: FetchContentRequest,
    service: ResearchService = Depends(get_research_service),
):
    return await service.fetch_content(payload, request_id=str(uuid4()))


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", provider="playwright-bing", version="0.1.0")


@router.get("/readyz", response_model=HealthResponse, summary="Readiness probe")
async def readyz() -> HealthResponse:
    return HealthResponse(status="ready", provider="playwright-bing", version="0.1.0")


@router.post("/health-check", response_model=HealthResponse, summary="Tool health operation")
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok", provider="playwright-bing", version="0.1.0")


async def validation_error_handler(_: object, exc: RequestValidationError) -> JSONResponse:
    message = exc.errors()[0].get("msg", "invalid request") if exc.errors() else "invalid request"
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "INVALID_REQUEST", "message": message}},
    )
