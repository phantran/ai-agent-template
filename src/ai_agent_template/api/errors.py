from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class ErrorResponse(BaseModel):
    type: str = Field(default="about:blank")
    title: str
    status: int
    detail: str | None = None
    request_id: str | None = None
    errors: list[dict[str, Any]] | None = None


def _problem(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str | None,
    type_: str = "about:blank",
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    body = ErrorResponse(
        type=type_,
        title=title,
        status=status_code,
        detail=detail,
        request_id=request_id,
        errors=errors,
    ).model_dump(exclude_none=True)
    headers = {"x-request-id": request_id} if request_id else None
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return _problem(
            request,
            status_code=exc.status_code,
            title=_status_title(exc.status_code),
            detail=str(exc.detail) if exc.detail else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _problem(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Validation failed",
            detail="One or more request fields are invalid.",
            type_="https://errors.ai-agent-template/validation",
            errors=[dict(error) for error in exc.errors()],
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            request_id=getattr(request.state, "request_id", None),
        )
        return _problem(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal server error",
            detail="An unexpected error occurred.",
        )


def _status_title(code: int) -> str:
    return {
        400: "Bad request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not found",
        409: "Conflict",
        413: "Payload too large",
        422: "Validation failed",
        429: "Too many requests",
        500: "Internal server error",
        503: "Service unavailable",
    }.get(code, "Error")
