from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from ai_agent_template.api.dependencies import get_app_settings
from ai_agent_template.core.settings import Settings

API_KEY_HEADER = "x-api-key"

_api_key_scheme = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


async def require_api_key(
    request: Request,
    api_key: Annotated[str | None, Depends(_api_key_scheme)] = None,
    settings: Annotated[Settings, Depends(get_app_settings)] = None,  # type: ignore[assignment]
) -> None:
    allowed = settings.auth_api_keys
    if not allowed:
        return
    if api_key and api_key in allowed:
        request.state.api_key_id = _api_key_label(api_key)
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key.",
        headers={"WWW-Authenticate": API_KEY_HEADER},
    )


def _api_key_label(api_key: str) -> str:
    if len(api_key) <= 4:
        return "***"
    return f"{api_key[:2]}***{api_key[-2:]}"
