from functools import lru_cache

from ai_agent_template.agent.checkpointer import build_checkpointer
from ai_agent_template.agent.graph import build_agent_graph
from ai_agent_template.agent.models import build_chat_model
from ai_agent_template.agent.service import AgentService
from ai_agent_template.core.settings import Settings, get_settings
from ai_agent_template.rag.service import EmptyRagRetriever, RagService
from ai_agent_template.rag.vectorstore import build_vector_store


@lru_cache(maxsize=1)
def get_agent_service() -> AgentService:
    settings = get_settings()
    model = build_chat_model(settings)
    retriever = get_rag_service() if settings.rag_enabled else EmptyRagRetriever()
    checkpointer = build_checkpointer(settings)
    graph = build_agent_graph(model, retriever=retriever, checkpointer=checkpointer)
    return AgentService(graph=graph)


@lru_cache(maxsize=1)
def get_rag_service() -> RagService:
    settings = get_settings()
    vector_store = build_vector_store(settings)
    return RagService(settings=settings, vector_store=vector_store)


def get_app_settings() -> Settings:
    return get_settings()
