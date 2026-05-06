import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ai_agent_template.agent.service import AgentService
from ai_agent_template.api.dependencies import get_agent_service
from ai_agent_template.api.schemas import AgentInvokeRequest, AgentInvokeResponse

router = APIRouter()
AgentServiceDependency = Annotated[AgentService, Depends(get_agent_service)]


@router.post("/invoke", response_model=AgentInvokeResponse)
async def invoke_agent(
    request: AgentInvokeRequest,
    agent_service: AgentServiceDependency,
) -> AgentInvokeResponse:
    return await agent_service.invoke(request)


@router.post("/stream")
async def stream_agent(
    request: AgentInvokeRequest,
    agent_service: AgentServiceDependency,
) -> StreamingResponse:
    return StreamingResponse(
        _format_sse(agent_service.stream(request)),
        media_type="text/event-stream",
        headers={
            "cache-control": "no-cache",
            "x-accel-buffering": "no",
        },
    )


async def _format_sse(events: AsyncIterator[dict[str, object]]) -> AsyncIterator[bytes]:
    async for event in events:
        event_type = str(event.get("type", "message"))
        payload = json.dumps({k: v for k, v in event.items() if k != "type"}, default=str)
        yield f"event: {event_type}\ndata: {payload}\n\n".encode()
