"""Cover request-id propagation, error envelope, auth, and rate limiting.

These tests bypass the LangGraph stack by overriding the agent service dependency,
so they exercise only the API edge.
"""

from collections.abc import AsyncIterator
from typing import Any, Protocol

import pytest
from fastapi.testclient import TestClient

import ai_agent_template.core.settings as settings_module
from ai_agent_template.api.app import create_app
from ai_agent_template.api.dependencies import get_agent_service, get_app_settings
from ai_agent_template.api.schemas import AgentInvokeRequest, AgentInvokeResponse
from ai_agent_template.core.settings import Settings


class _ClientFactory(Protocol):
    def __call__(self, **settings_overrides: Any) -> TestClient: ...


class _StubService:
    async def invoke(self, request: AgentInvokeRequest) -> AgentInvokeResponse:
        return AgentInvokeResponse(message=f"echo:{request.message}", thread_id=request.thread_id)

    async def stream(self, request: AgentInvokeRequest) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "delta", "text": "hi"}
        yield {"type": "done", "thread_id": request.thread_id}


@pytest.fixture
def make_client(monkeypatch: pytest.MonkeyPatch) -> _ClientFactory:
    def _factory(**settings_overrides: Any) -> TestClient:
        settings = Settings(**settings_overrides)
        # Middleware reads `get_settings()` at app construction.
        monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
        app = create_app()
        # FastAPI dependency injection — canonical override path for runtime deps.
        app.dependency_overrides[get_app_settings] = lambda: settings
        app.dependency_overrides[get_agent_service] = lambda: _StubService()
        return TestClient(app)

    return _factory


def test_request_id_is_echoed_back(make_client: _ClientFactory) -> None:
    client = make_client(rate_limit_enabled=False)
    response = client.post(
        "/v1/agent/invoke",
        json={"message": "hello"},
        headers={"x-request-id": "req-abc"},
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-abc"


def test_request_id_generated_when_missing(make_client: _ClientFactory) -> None:
    client = make_client(rate_limit_enabled=False)
    response = client.post("/v1/agent/invoke", json={"message": "hello"})
    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_validation_error_returns_problem_envelope(make_client: _ClientFactory) -> None:
    client = make_client(rate_limit_enabled=False)
    response = client.post("/v1/agent/invoke", json={"message": ""})
    assert response.status_code == 422
    body = response.json()
    assert body["title"] == "Validation failed"
    assert body["status"] == 422
    assert body["request_id"]


def test_auth_required_when_keys_configured(make_client: _ClientFactory) -> None:
    client = make_client(rate_limit_enabled=False, auth_api_keys=["secret-1"])

    unauth = client.post("/v1/agent/invoke", json={"message": "hi"})
    assert unauth.status_code == 401
    assert unauth.json()["title"] == "Unauthorized"

    ok = client.post(
        "/v1/agent/invoke",
        json={"message": "hi"},
        headers={"x-api-key": "secret-1"},
    )
    assert ok.status_code == 200


def test_health_is_not_protected_or_rate_limited(make_client: _ClientFactory) -> None:
    client = make_client(rate_limit_enabled=True, auth_api_keys=["secret-1"], rate_limit_requests=1)
    for _ in range(5):
        response = client.get("/health/live")
        assert response.status_code == 200


def test_rate_limit_engages_after_window_exhaustion(make_client: _ClientFactory) -> None:
    client = make_client(
        rate_limit_enabled=True, rate_limit_requests=2, rate_limit_window_seconds=60
    )

    a = client.post("/v1/agent/invoke", json={"message": "1"})
    b = client.post("/v1/agent/invoke", json={"message": "2"})
    c = client.post("/v1/agent/invoke", json={"message": "3"})

    assert a.status_code == 200
    assert b.status_code == 200
    assert c.status_code == 429
    assert c.headers["retry-after"]
    assert c.json()["title"] == "Too many requests"


def test_cors_preflight_succeeds_without_auth(make_client: _ClientFactory) -> None:
    client = make_client(
        rate_limit_enabled=True,
        rate_limit_requests=1,
        auth_api_keys=["secret-1"],
        cors_allowed_origins=["http://localhost:5173"],
    )
    response = client.options(
        "/v1/agent/invoke",
        headers={
            "origin": "http://localhost:5173",
            "access-control-request-method": "POST",
            "access-control-request-headers": "x-api-key,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "x-api-key" in response.headers["access-control-allow-headers"].lower()


def test_cors_headers_present_on_rate_limited_response(make_client: _ClientFactory) -> None:
    client = make_client(
        rate_limit_enabled=True,
        rate_limit_requests=1,
        rate_limit_window_seconds=60,
        cors_allowed_origins=["http://localhost:5173"],
    )
    headers = {"origin": "http://localhost:5173"}
    first = client.post("/v1/agent/invoke", json={"message": "1"}, headers=headers)
    limited = client.post("/v1/agent/invoke", json={"message": "2"}, headers=headers)

    assert first.status_code == 200
    assert limited.status_code == 429
    # CORS must wrap the inner middleware's early response, otherwise the browser
    # masks the 429 as a generic CORS error.
    assert limited.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_stream_endpoint_emits_sse_events(make_client: _ClientFactory) -> None:
    client = make_client(rate_limit_enabled=False)
    with client.stream("POST", "/v1/agent/stream", json={"message": "hi"}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = b"".join(response.iter_bytes()).decode()
    assert "event: delta" in body
    assert "event: done" in body
