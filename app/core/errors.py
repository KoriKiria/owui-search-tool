from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class UnauthorizedError(ApiError):
    def __init__(self, message: str = "invalid bearer token") -> None:
        super().__init__(401, "UNAUTHORIZED", message)


class InvalidRequestError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(400, "INVALID_REQUEST", message)


class UpstreamFailureError(ApiError):
    def __init__(self, message: str = "search provider unavailable") -> None:
        super().__init__(502, "UPSTREAM_FAILURE", message)


class InternalFailureError(ApiError):
    def __init__(self, message: str = "unexpected server error") -> None:
        super().__init__(500, "INTERNAL_ERROR", message)


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
