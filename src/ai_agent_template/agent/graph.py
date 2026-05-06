from typing import Any, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ai_agent_template.agent.state import AgentState
from ai_agent_template.rag.service import EmptyRagRetriever, RagRetriever

SYSTEM_PROMPT = """You are a production AI agent.
Be concise, truthful, and practical. Ask for missing information when needed.
When retrieval context is provided:
- Ground your answer in that context.
- Cite only the exact source labels shown in square brackets.
- Do not invent papers, URLs, authors, or source labels.
- If the context is insufficient, say what is missing.
When voice samples are provided:
- Use them to infer tone, cadence, vocabulary, sentence length, and level of warmth.
- Do not copy long passages from the samples.
- Preserve the user's meaning.
- Avoid adding facts not present in the user draft or retrieval context.
"""


class SupportsAInvoke(Protocol):
    async def ainvoke(self, graph_input: list[BaseMessage]) -> BaseMessage: ...


def build_agent_graph(
    model: BaseChatModel | SupportsAInvoke,
    retriever: RagRetriever | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, None, Any, Any]:
    workflow = StateGraph(AgentState)
    rag_retriever = retriever or EmptyRagRetriever()

    def retrieve(state: AgentState) -> AgentState:
        latest_message = state["messages"][-1]
        query = str(latest_message.content)
        return {
            "messages": state["messages"],
            "sources": rag_retriever.search(query),
            "voice_samples": rag_retriever.search_voice(query),
        }

    async def call_model(state: AgentState) -> AgentState:
        context = format_sources(state.get("sources", []))
        voice_context = format_voice_samples(state.get("voice_samples", []))
        system_prompt = SYSTEM_PROMPT
        if context:
            system_prompt = f"{SYSTEM_PROMPT}\n\nRetrieval context:\n{context}"
        if voice_context:
            system_prompt = f"{system_prompt}\n\nVoice samples:\n{voice_context}"

        messages = [SystemMessage(content=system_prompt), *state["messages"]]
        response = await model.ainvoke(messages)
        if not isinstance(response, AIMessage):
            response = AIMessage(content=str(response.content))
        return {
            "messages": [*state["messages"], response],
            "sources": state.get("sources", []),
            "voice_samples": state.get("voice_samples", []),
        }

    workflow.add_node("retrieve", retrieve)
    workflow.add_node("agent", call_model)
    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "agent")
    workflow.add_edge("agent", END)
    return workflow.compile(checkpointer=checkpointer) if checkpointer else workflow.compile()


def initial_state(message: str) -> AgentState:
    return {"messages": [HumanMessage(content=message)], "sources": [], "voice_samples": []}


def format_sources(sources: list[Any]) -> str:
    lines: list[str] = []
    for index, source in enumerate(sources, start=1):
        lines.append(f"[{source.source}] {source.content}")
        if source.metadata:
            lines.append(f"metadata: {source.metadata}")
        if index < len(sources):
            lines.append("")
    return "\n".join(lines)


def format_voice_samples(sources: list[Any]) -> str:
    lines: list[str] = []
    for index, source in enumerate(sources, start=1):
        lines.append(f"[voice:{source.source}] {source.content}")
        if index < len(sources):
            lines.append("")
    return "\n".join(lines)
