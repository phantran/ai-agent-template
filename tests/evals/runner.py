"""Lightweight eval harness.

Runs each case against the configured agent and asserts simple inclusion rules.
Designed as a regression gate, not a leaderboard. Replace `must_include_any`
checks with model-graded scoring when you outgrow string assertions.

Usage:
    uv run python -m tests.evals.runner            # uses real model
    uv run python -m tests.evals.runner --offline  # uses a stub graph
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage

from ai_agent_template.agent.graph import build_agent_graph
from ai_agent_template.agent.service import AgentService
from ai_agent_template.api.schemas import AgentInvokeRequest

GOLDEN = Path(__file__).parent / "golden.jsonl"


@dataclass(frozen=True)
class EvalCase:
    id: str
    input: str
    must_include_any: tuple[str, ...]
    must_exclude: tuple[str, ...]


def load_cases(path: Path = GOLDEN) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        cases.append(
            EvalCase(
                id=record["id"],
                input=record["input"],
                must_include_any=tuple(record.get("must_include_any", [])),
                must_exclude=tuple(record.get("must_exclude", [])),
            )
        )
    return cases


def grade(case: EvalCase, output: str) -> tuple[bool, str]:
    text = output.lower()
    if case.must_exclude and any(term.lower() in text for term in case.must_exclude):
        bad = next(term for term in case.must_exclude if term.lower() in text)
        return False, f"contains forbidden term: {bad!r}"
    if case.must_include_any and not any(term.lower() in text for term in case.must_include_any):
        return False, f"missing any of: {case.must_include_any!r}"
    return True, "ok"


class _StubGraph:
    """Offline graph that returns a deterministic answer covering the eval terms."""

    async def ainvoke(
        self, state: dict[str, Any], config: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        text = (
            "Production agents need evals, tracing, auth, rate limits, and rollback plans. "
            "ready. If retrieval context is missing, this answer says so explicitly."
        )
        return {"messages": [*state["messages"], AIMessage(content=text)], "sources": []}

    async def astream(
        self, *args: Any, **kwargs: Any
    ) -> AsyncIterator[Any]:  # pragma: no cover - unused
        if False:
            yield None


async def _run(service: AgentService, cases: Iterable[EvalCase]) -> int:
    cases_list = list(cases)
    failures = 0
    for case in cases_list:
        start = perf_counter()
        response = await service.invoke(AgentInvokeRequest(message=case.input))
        elapsed_ms = (perf_counter() - start) * 1000
        passed, reason = grade(case, response.message)
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {case.id} ({elapsed_ms:.0f}ms) — {reason}")
        if not passed:
            failures += 1
    print(f"\n{len(cases_list)} cases run; {failures} failed.")
    return failures


def _build_service(offline: bool) -> AgentService:
    if offline:
        return AgentService(_StubGraph())
    from ai_agent_template.agent.models import build_chat_model
    from ai_agent_template.core.settings import get_settings

    settings = get_settings()
    model = build_chat_model(settings)
    graph = build_agent_graph(model)
    return AgentService(graph=graph)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Use a deterministic stub graph.")
    args = parser.parse_args(argv)

    cases = load_cases()
    service = _build_service(args.offline)
    failures = asyncio.run(_run(service, cases))
    return 0 if failures == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
