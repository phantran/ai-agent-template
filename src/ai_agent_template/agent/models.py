from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from ai_agent_template.core.settings import Settings


def build_chat_model(settings: Settings) -> BaseChatModel:
    match settings.model_provider:
        case "groq":
            return ChatGroq(
                api_key=settings.groq_api_key,
                model_name=settings.model_name,
                temperature=settings.model_temperature,
                timeout=settings.model_timeout_seconds,
                max_retries=settings.model_max_retries,
            )
        case "openai":
            return ChatOpenAI(
                api_key=settings.openai_api_key,
                model=settings.model_name,
                temperature=settings.model_temperature,
                timeout=settings.model_timeout_seconds,
                max_retries=settings.model_max_retries,
            )
