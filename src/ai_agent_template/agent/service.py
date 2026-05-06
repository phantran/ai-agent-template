from collections.abc import AsyncIterator
from typing import Any, cast

from langchain_core.messages import AIMessage, AIMessageChunk

from ai_agent_template.agent.graph import initial_state
from ai_agent_template.api.schemas import AgentInvokeRequest, AgentInvokeResponse
from ai_agent_template.observability.tracing import agent_span
from ai_agent_template.rag.schemas import RagSource

# `Any` because LangGraph's CompiledStateGraph has overloaded `astream` signatures
# that no narrow Protocol can match. The service treats it as a runnable with
# `ainvoke` and `astream` — those are validated structurally at call time.
AgentGraph = Any


class AgentService:
    def __init__(self, graph: AgentGraph) -> None:
        self._graph = graph

    async def invoke(self, request: AgentInvokeRequest) -> AgentInvokeResponse:
        config = self._config(request.thread_id)
        with agent_span("agent.invoke", thread_id=request.thread_id):
            result = cast(
                dict[str, Any],
                await self._graph.ainvoke(initial_state(request.message), config=config),
            )
        messages = result.get("messages", [])
        sources = [source for source in result.get("sources", []) if isinstance(source, RagSource)]
        final_message = messages[-1] if messages else AIMessage(content="")
        return AgentInvokeResponse(
            message=str(final_message.content),
            thread_id=request.thread_id,
            sources=sources,
        )

    async def stream(self, request: AgentInvokeRequest) -> AsyncIterator[dict[str, Any]]:
        """Yield SSE-friendly events: token deltas, sources, and a final done event."""
        config = self._config(request.thread_id)
        sources_emitted = False
        with agent_span("agent.stream", thread_id=request.thread_id):
            async for mode, chunk in self._graph.astream(
                initial_state(request.message),
                config=config,
                stream_mode=["updates", "messages"],
            ):
                if mode == "updates":
                    sources = _extract_sources(chunk)
                    if sources and not sources_emitted:
                        sources_emitted = True
                        yield {
                            "type": "sources",
                            "sources": [s.model_dump() for s in sources],
                        }
                elif mode == "messages":
                    message_chunk, metadata = chunk
                    if isinstance(message_chunk, AIMessageChunk):
                        text = str(message_chunk.content)
                        if text:
                            yield {
                                "type": "delta",
                                "text": text,
                                "node": metadata.get("langgraph_node") if metadata else None,
                            }
        yield {"type": "done", "thread_id": request.thread_id}

    @staticmethod
    def _config(thread_id: str | None) -> dict[str, Any] | None:
        if not thread_id:
            return None
        return {"configurable": {"thread_id": thread_id}}


def _extract_sources(update: dict[str, Any]) -> list[RagSource]:
    if not isinstance(update, dict):
        return []
    for node_state in update.values():
        if not isinstance(node_state, dict):
            continue
        candidates = node_state.get("sources", [])
        if candidates:
            return [s for s in candidates if isinstance(s, RagSource)]
    return []
