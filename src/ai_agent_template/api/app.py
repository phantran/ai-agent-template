from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_agent_template.api.errors import register_exception_handlers
from ai_agent_template.api.middleware import install_middleware
from ai_agent_template.api.routes import agent, health, rag
from ai_agent_template.api.security import require_api_key
from ai_agent_template.core import settings as settings_module
from ai_agent_template.core.logging import configure_logging
from ai_agent_template.observability.tracing import configure_tracing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = settings_module.get_settings()
    configure_logging(settings)
    configure_tracing(app, settings)
    yield


def create_app() -> FastAPI:
    settings = settings_module.get_settings()
    app = FastAPI(
        title=settings.service_name,
        version="0.1.0",
        docs_url="/docs" if settings.is_local else None,
        redoc_url="/redoc" if settings.is_local else None,
        lifespan=lifespan,
    )
    # Inner middleware first; CORS is added last so it ends up outermost and
    # its headers make it onto every response (including 401/413/422/429
    # envelopes that the inner middleware can return early).
    install_middleware(app, settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=[
            "authorization",
            "content-type",
            "x-api-key",
            "x-request-id",
        ],
        expose_headers=[
            "x-request-id",
            "x-ratelimit-limit",
            "x-ratelimit-remaining",
            "retry-after",
        ],
        max_age=600,
    )
    register_exception_handlers(app)

    protected = [Depends(require_api_key)]
    app.include_router(health.router, tags=["health"])
    app.include_router(agent.router, prefix="/v1/agent", tags=["agent"], dependencies=protected)
    app.include_router(rag.router, prefix="/v1/rag", tags=["rag"], dependencies=protected)
    return app
