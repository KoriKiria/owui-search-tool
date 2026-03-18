from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import UnauthorizedError


def require_bearer_token(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.auth_enabled:
        return

    expected = settings.api_bearer_token
    if not expected:
        raise UnauthorizedError("authentication is enabled but no bearer token is configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError()
    if authorization.removeprefix("Bearer ").strip() != expected:
        raise UnauthorizedError()
