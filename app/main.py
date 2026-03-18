from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import ApiError, InternalFailureError, api_error_handler
from app.core.logging import configure_logging
from app.routes.tool import router, validation_error_handler


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="search-tool",
        description="OpenAPI tool server for Open WebUI agent search workflows",
        version="0.1.0",
    )
    origins = settings.cors_allow_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if origins == "*" else list(origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc: Exception):
        if isinstance(exc, ApiError):
            return await api_error_handler(request, exc)
        return await api_error_handler(request, InternalFailureError())

    return app


app = create_app()
