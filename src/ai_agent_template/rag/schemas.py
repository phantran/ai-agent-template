from typing import Any, Literal

from pydantic import BaseModel, Field


class RagSource(BaseModel):
    source: str
    content: str
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagIngestRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1, max_length=512)
    document_type: Literal["knowledge", "voice_sample"] = "knowledge"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagIngestResponse(BaseModel):
    source: str
    chunks: int


class RagSearchResponse(BaseModel):
    query: str
    sources: list[RagSource]
