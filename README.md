# AI Agent Template

An opinionated open source scaffold for production-grade AI agents built with FastAPI, LangChain, and LangGraph.

This repository is intentionally small at the core and serious at the edges: typed configuration, explicit graph composition, health checks, structured logging, OpenTelemetry hooks, tests, Docker, CI, and clean extension points for tools, memory, persistence, and model providers.

## What You Get

- FastAPI application with versioned routes, lifecycle setup, and a `text/event-stream` streaming endpoint.
- LangGraph workflow with a typed state object, injectable chat model, and pluggable checkpointer (`thread_id` memory across turns).
- LangChain model integrations through `langchain-groq` and `langchain-openai`.
- Request and response schemas for synchronous and streaming agent turns.
- RAG ingestion (idempotent re-ingest via content-hash chunk IDs), retrieval search, optional reranker hook, and source-cited agent responses.
- Health and readiness endpoints.
- API edge hardening: optional API-key auth, in-process sliding-window rate limit, request-id propagation, body-size guard, RFC 7807-style error envelope, structured per-request logs.
- Environment-driven settings through `pydantic-settings`.
- Structured JSON logs suitable for container platforms.
- Optional OpenTelemetry OTLP export with explicit spans around agent invocation, RAG ingest, and search.
- Eval harness with a JSONL golden set and an offline regression runner (`make eval-offline`).
- `uv`-based Python packaging.
- Ruff, mypy, pytest, coverage, pre-commit, Docker, Compose, and GitHub Actions.

## Quickstart

```bash
uv sync --all-extras --dev
cp .env.example .env
uv run fastapi dev src/ai_agent_template/main.py
```

The API will be available at `http://127.0.0.1:8000`.

To launch the API, frontend console, and Qdrant together:

```bash
cp .env.example .env
docker compose up --build
```

Then open `http://127.0.0.1:5173`.

```bash
curl -X POST http://127.0.0.1:8000/v1/agent/invoke \
  -H "Content-Type: application/json" \
  -d '{"message":"Give me a concise launch checklist for an AI agent.","thread_id":"demo"}'
```

## RAG Quickstart

Add knowledge with JSON:

```bash
curl -X POST http://127.0.0.1:8000/v1/rag/documents \
  -H "Content-Type: application/json" \
  -d '{"source":"launch-notes","text":"Production agents need evals, tracing, auth, rate limits, and rollback plans.","metadata":{"kind":"note"}}'
```

Or upload files through the frontend console. Supported local file types are `.txt`, `.md`, `.markdown`, `.json`, and `.pdf`.

Test retrieval:

```bash
curl "http://127.0.0.1:8000/v1/rag/search?q=what%20does%20production%20need"
```

By default, local development expects the Qdrant service at `http://localhost:6333` and uses local FastEmbed embeddings. `docker compose up --build` starts Qdrant for you. For quick single-process experiments only, you can clear `AI_AGENT_QDRANT_URL` to use embedded local storage at `.qdrant`.

## Voice Samples

To help the agent humanize drafts in your voice, store examples of your own writing as `voice_sample` documents:

```bash
curl -X POST http://127.0.0.1:8000/v1/rag/voice-samples \
  -H "Content-Type: application/json" \
  -d '{"source":"my-note-2026-05","text":"Paste a piece of writing that genuinely sounds like you.","document_type":"voice_sample","metadata":{"kind":"writing_sample"}}'
```

The frontend Knowledge panel has a `Voice` toggle for pasted samples and file uploads. During agent calls, the graph retrieves factual knowledge and voice samples separately, then asks the model to preserve meaning while matching tone, cadence, vocabulary, and warmth. It is prompted not to copy long passages from your samples.

## Frontend Console

The repository includes a React 19 + Vite 7 + Tailwind CSS v4 console under `frontend/`, using shadcn/ui-style local components, Radix primitives, TanStack Query, Sonner, and lucide icons. It includes chat, knowledge ingestion, voice-sample ingestion, file upload, retrieval search, and response source display.

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173` while the FastAPI server is running on `http://127.0.0.1:8000`.

Set `VITE_API_BASE_URL` if your API runs somewhere else.

To build the console:

```bash
cd frontend
npm run build
```

## Configuration

Set these in `.env` or your deployment environment:

```bash
GROQ_API_KEY=gsk_...
AI_AGENT_ENVIRONMENT=local
AI_AGENT_LOG_LEVEL=INFO
AI_AGENT_MODEL_PROVIDER=groq
AI_AGENT_MODEL_NAME=llama-3.1-8b-instant
AI_AGENT_RAG_ENABLED=true
AI_AGENT_QDRANT_URL=
AI_AGENT_OTEL_ENABLED=false
```

The default provider is Groq with `llama-3.1-8b-instant`, which is a fast, low-friction option for trying the scaffold. Create a Groq API key in the Groq console and set `GROQ_API_KEY`.

To use OpenAI instead:

```bash
OPENAI_API_KEY=sk-...
AI_AGENT_MODEL_PROVIDER=openai
AI_AGENT_MODEL_NAME=gpt-4o-mini
```

Use whichever OpenAI model your account has access to (e.g. `gpt-4o`, `gpt-4o-mini`, `o4-mini`).

### Auth and rate limiting

```bash
AI_AGENT_AUTH_API_KEYS=["dev-key-1","dev-key-2"]
AI_AGENT_RATE_LIMIT_ENABLED=true
AI_AGENT_RATE_LIMIT_REQUESTS=60
AI_AGENT_RATE_LIMIT_WINDOW_SECONDS=60
```

When `auth_api_keys` is empty, auth is disabled (template defaults). When populated, every `/v1/*` request must send `x-api-key: <one-of-the-keys>`. Rate limits are enforced per API key (or per client IP when no key is supplied) using an in-process sliding window — fine for single-replica deployments, swap for Redis when you scale out.

Each response includes an `x-request-id` header (echoes the inbound one, or generates a UUID), and structured logs include the request id, path, method, status, and duration.

### Streaming

```bash
curl -N -X POST http://127.0.0.1:8000/v1/agent/stream \
  -H "Content-Type: application/json" \
  -H "x-api-key: dev-key-1" \
  -d '{"message":"Stream me a five-step launch plan.","thread_id":"demo"}'
```

Events:

- `sources` — retrieved RAG chunks (emitted once before tokens).
- `delta` — incremental token text from the model.
- `done` — end of stream.

## Development

```bash
make lint          # ruff check
make format        # ruff format
make typecheck     # mypy strict
make test          # pytest with coverage
make eval-offline  # run the agent eval harness against the stub graph
make eval          # run the eval harness against the configured live model
```

## Project Shape

```text
src/ai_agent_template/
  api/              FastAPI routers and schemas
  agent/            LangGraph state, graph factory, service layer
  core/             settings, logging, app lifecycle dependencies
  observability/    tracing setup
  rag/              ingestion, chunking, embeddings, Qdrant retrieval
frontend/           React/Vite agent test console
```

## Extension Points

- Add tools in `src/ai_agent_template/agent/tools.py`.
- Replace the model factory in `src/ai_agent_template/agent/models.py`.
- Add persistence and checkpointing in `src/ai_agent_template/agent/graph.py`.
- Add authentication, rate limiting, and tenant context at the API boundary.

See [docs/architecture.md](docs/architecture.md) for the deeper production roadmap.

## License

MIT
