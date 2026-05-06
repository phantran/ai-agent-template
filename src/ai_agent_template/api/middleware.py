from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from threading import Lock
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ai_agent_template.core.settings import Settings

logger = structlog.get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, header_name: str = "x-request-id") -> None:
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(self._header_name) or uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception("request_failed", elapsed_ms=round(elapsed_ms, 2))
            structlog.contextvars.unbind_contextvars("request_id", "method", "path")
            raise
        else:
            elapsed_ms = (time.perf_counter() - start) * 1000
            response.headers[self._header_name] = request_id
            logger.info(
                "request_completed",
                status_code=response.status_code,
                elapsed_ms=round(elapsed_ms, 2),
            )
        finally:
            structlog.contextvars.unbind_contextvars("request_id", "method", "path")
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-process sliding-window rate limit. Keyed by API key when present, else client IP.

    Suitable for single-instance deployments and tests. For multi-instance, swap in
    a Redis-backed limiter behind the same interface.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_requests: int,
        window_seconds: int,
        exempt_paths: tuple[str, ...] = ("/health/live", "/health/ready"),
    ) -> None:
        super().__init__(app)
        self._max = max_requests
        self._window = window_seconds
        self._exempt = exempt_paths
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Don't count CORS preflights or health checks against the budget.
        if request.method == "OPTIONS" or request.url.path in self._exempt:
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._max:
                retry_after = max(1, int(self._window - (now - bucket[0])))
                return _rate_limited_response(retry_after, self._max, 0)
            bucket.append(now)
            remaining = self._max - len(bucket)

        response = await call_next(request)
        response.headers["x-ratelimit-limit"] = str(self._max)
        response.headers["x-ratelimit-remaining"] = str(remaining)
        return response

    @staticmethod
    def _client_key(request: Request) -> str:
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"key:{api_key}"
        client = request.client
        return f"ip:{client.host}" if client else "ip:unknown"


def _rate_limited_response(retry_after: int, limit: int, remaining: int) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "type": "https://errors.ai-agent-template/rate-limited",
            "title": "Too many requests",
            "status": 429,
            "detail": "Rate limit exceeded. Try again later.",
        },
        headers={
            "retry-after": str(retry_after),
            "x-ratelimit-limit": str(limit),
            "x-ratelimit-remaining": str(remaining),
        },
    )


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        super().__init__(app)
        self._max = max_bytes

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > self._max:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={
                    "type": "about:blank",
                    "title": "Payload too large",
                    "status": 413,
                    "detail": f"Request body exceeds {self._max} bytes.",
                },
            )
        return await call_next(request)


def install_middleware(app: FastAPI, settings: Settings) -> None:
    if settings.rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            max_requests=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.request_max_body_bytes)
    app.add_middleware(RequestContextMiddleware, header_name=settings.request_id_header)


__all__ = (
    "BodySizeLimitMiddleware",
    "RateLimitMiddleware",
    "RequestContextMiddleware",
    "install_middleware",
)
