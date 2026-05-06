from pydantic import BaseModel, Field

from ai_agent_template.rag.schemas import RagSource


class AgentInvokeRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=16_000)
    thread_id: str | None = Field(default=None, max_length=256)


class AgentInvokeResponse(BaseModel):
    message: str
    thread_id: str | None = None
    sources: list[RagSource] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
