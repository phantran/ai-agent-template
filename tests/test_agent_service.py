from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from ai_agent_template.agent.service import AgentService
from ai_agent_template.api.schemas import AgentInvokeRequest
from ai_agent_template.rag.schemas import RagSource


class FakeGraph:
    async def ainvoke(
        self,
        input: dict[str, Any],  # noqa: A002 - match LangGraph/LangChain runnable API.
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        assert input["messages"][0].content == "hello"
        assert config == {"configurable": {"thread_id": "thread-1"}}
        return {"messages": [*input["messages"], AIMessage(content="world")], "sources": []}

    async def astream(
        self,
        input: dict[str, Any],  # noqa: A002 - match LangGraph/LangChain runnable API.
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        yield (
            "updates",
            {"retrieve": {"sources": [RagSource(source="kb", content="x")]}},
        )
        yield ("messages", (AIMessageChunk(content="hello "), {"langgraph_node": "agent"}))
        yield ("messages", (AIMessageChunk(content="world"), {"langgraph_node": "agent"}))


@pytest.mark.asyncio
async def test_agent_service_invokes_graph() -> None:
    service = AgentService(FakeGraph())

    response = await service.invoke(AgentInvokeRequest(message="hello", thread_id="thread-1"))

    assert response.message == "world"
    assert response.thread_id == "thread-1"
    assert response.sources == []


@pytest.mark.asyncio
async def test_agent_service_streams_deltas_and_sources() -> None:
    service = AgentService(FakeGraph())

    events = [event async for event in service.stream(AgentInvokeRequest(message="hi"))]

    types = [event["type"] for event in events]
    assert types[0] == "sources"
    assert events[0]["sources"][0]["source"] == "kb"
    assert "delta" in types
    assert types[-1] == "done"
