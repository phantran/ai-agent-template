FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --no-dev --no-install-project && uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "fastapi", "run", "src/ai_agent_template/main.py", "--host", "0.0.0.0", "--port", "8000"]
