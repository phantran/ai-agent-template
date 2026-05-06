"""Pluggable LangGraph checkpointer factory.

The default in-memory backend is fine for local dev and tests. For multi-replica
production, swap in a durable backend (Postgres, Redis) by extending this factory
and adding the dependency under the matching `[project.optional-dependencies]`
group in pyproject.toml.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from ai_agent_template.core.settings import Settings


def build_checkpointer(settings: Settings) -> BaseCheckpointSaver[Any] | None:
    if settings.agent_checkpoint_backend == "none":
        return None
    if settings.agent_checkpoint_backend == "memory":
        return InMemorySaver()
    raise ValueError(f"Unknown checkpoint backend: {settings.agent_checkpoint_backend}")
