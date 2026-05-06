# Architecture

See [architecture-diagrams.md](architecture-diagrams.md) for Mermaid diagrams of the runtime, streaming path, RAG ingestion, and Docker Compose topology.

## Layers

```
Client ─▶ API edge (middleware + auth) ─▶ AgentService ─▶ LangGraph
                                                ├── retrieve  ─▶ RagService ─▶ Qdrant
                                                └── model     ─▶ Groq / OpenAI
```

## API Edge

Every `/v1/*` request passes through these middleware layers, in order:

1. **CORS** — origins from `AI_AGENT_CORS_ALLOWED_ORIGINS`.
2. **Rate limit** — sliding-window, in-process. Keyed by `x-api-key` if present, else client IP. `/health/*` is exempt. Returns 429 with `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`. For multi-replica deployments, swap the limiter for a Redis-backed implementation behind the same interface.
3. **Body size** — rejects requests over `AI_AGENT_REQUEST_MAX_BODY_BYTES` with 413.
4. **Request context** — propagates the inbound request id (or generates a UUID), attaches it to `request.state`, binds it into structured-log context (`structlog.contextvars`), echoes it on the response header, and emits a `request_completed` log line with method, path, status, and duration.

After middleware, the routers under `/v1/*` enforce **API-key auth** when `AI_AGENT_AUTH_API_KEYS` is non-empty. Auth is disabled by default to keep the template friction-free; populate the list to turn it on.

Errors from anywhere in the request path are normalized through a single envelope (RFC 7807-style `ErrorResponse`) with `type`, `title`, `status`, `detail`, `request_id`, and an optional `errors` array for validation failures. Unhandled exceptions are logged with stack and request id, and clients get a generic 500 envelope (no leaked internals).

## Runtime Path

1. FastAPI receives `POST /v1/agent/invoke` (or `/v1/agent/stream`).
2. Middleware stamps a request id, applies rate limit, and structured-logs entry/exit.
3. The protected router dependency validates the API key (when configured).
4. Pydantic validates the request schema.
5. `AgentService.invoke` (or `.stream`) opens an `agent.invoke` / `agent.stream` OpenTelemetry span and calls the compiled LangGraph.
6. The `retrieve` node calls `RagService.search` and `RagService.search_voice` (when RAG is enabled), each opening their own `rag.search` span.
7. The `model` node prompts the chat model with the system prompt, retrieved context, and voice samples.
8. **Invoke**: returns the final assistant message plus citations.
   **Stream**: yields a `sources` SSE event once retrieval completes, then incremental `delta` events for each token chunk, then a final `done` event.

## Streaming

`POST /v1/agent/stream` returns `text/event-stream`. The service consumes LangGraph's `astream(stream_mode=["updates", "messages"])`:

- `updates` events surface state diffs from each node — used to emit `sources` after the retrieve node fires.
- `messages` events surface `AIMessageChunk` deltas from the model node — re-encoded as SSE `delta` events.

Cache headers (`cache-control: no-cache`, `x-accel-buffering: no`) prevent intermediate proxies from buffering the stream.

## Checkpointing

`build_checkpointer(settings)` returns a LangGraph `BaseCheckpointSaver`:

- `memory` (default) — `InMemorySaver`, keyed by `thread_id`. Lets a client carry conversational state across `/v1/agent/invoke` calls within a single replica.
- `none` — no checkpointing.

For durable, multi-replica memory, add a backend (e.g. `langgraph-checkpoint-postgres`) and extend the factory. The graph compiles with persistence only when a checkpointer is supplied.

## RAG

### Ingestion

1. Documents enter through `/v1/rag/documents` (JSON), `/v1/rag/files` (multipart), `/v1/rag/voice-samples`, or `/v1/rag/voice-files`.
2. `RecursiveCharacterTextSplitter` chunks text with overlap.
3. Each chunk gets a deterministic UUIDv5 id derived from `(source, document_type, sha256(content))`. Re-ingesting the same text produces the same ids, so Qdrant upserts instead of duplicating.
4. `FastEmbedEmbeddings` produces a local dense embedding.
5. `QdrantVectorStore` writes the vectors and metadata.
6. The whole step runs inside a `rag.ingest` span (source, document type, char count, chunk count).

### Retrieval

1. The graph calls `search(query)` and `search_voice(query)` separately so factual context and voice samples never collide.
2. The service over-fetches by `rag_search_multiplier × top_k` so type filtering doesn't starve top-k when the collection is mixed.
3. An optional `Reranker` (cross-encoder, LLM judge, or anything else satisfying the protocol) can reorder the candidates before they hit the prompt.
4. Each retrieval runs inside a `rag.search` span (document type, k, fetch_k, result count).

### Voice Samples

Voice samples live in the same collection as factual knowledge but with `document_type=voice_sample`. The graph retrieves them in a separate pass and the model uses them only for tone, cadence, vocabulary, and warmth. The system prompt explicitly forbids copying long passages or inventing facts beyond the user's draft and retrieval context.

For local development prefer the Qdrant server from Docker Compose; embedded Qdrant storage works for one-off experiments but file locking can bite under auto-reload or multi-worker.

## Observability

`configure_tracing` wires OTLP gRPC export and `FastAPIInstrumentor` when `AI_AGENT_OTEL_ENABLED=true`. The `agent_span()` helper opens spans around:

- `agent.invoke` / `agent.stream`
- `rag.ingest`
- `rag.search`

Spans no-op safely when tracing is disabled (the OTEL API returns a no-op tracer). Logs are JSON via `structlog`, with `request_id` bound on every line emitted within a request.

## Frontend Console

`frontend/` is a separate React/Vite app. It:

- Calls `streamAgent` against `POST /v1/agent/stream` and renders token deltas live with sources rendered as soon as the `sources` event arrives.
- Sends `x-api-key` from `VITE_API_KEY` when present (matches the backend auth dependency).
- Parses error envelopes (`detail` / `title`) for toast messages.
- Invalidates the retrieval query cache after ingestion so freshly added knowledge is searchable on the next test query.

Configure with `VITE_API_BASE_URL` and `VITE_API_KEY`.

## Model Providers

`AI_AGENT_MODEL_PROVIDER` selects between Groq and OpenAI. Groq is the default for fast, low-friction local trials; OpenAI is available for teams that want frontier models. The factory in `agent/models.py` is the single extension point — add other providers there.

## Evaluation

`tests/evals/` ships a small JSONL golden set and a runner:

- `make eval-offline` — uses a deterministic stub graph; exits non-zero on regression. Suitable for CI gates.
- `make eval` — runs against the configured live model. Useful for prompt or model changes.

Grading is intentionally simple (`must_include_any`, `must_exclude`). Replace it with model-graded scoring when string assertions stop being enough.

## Configuration Surface

Most behavior is environment-driven through `pydantic-settings` in `core/settings.py`. Highlights:

| Setting                                  | Purpose                                                                 |
| ---------------------------------------- | ----------------------------------------------------------------------- |
| `AI_AGENT_AUTH_API_KEYS`                 | JSON list of valid API keys. Empty = auth off.                          |
| `AI_AGENT_RATE_LIMIT_*`                  | Enable/disable, requests per window, window seconds.                    |
| `AI_AGENT_REQUEST_MAX_BODY_BYTES`        | Body-size guard (default 5 MiB).                                        |
| `AI_AGENT_AGENT_CHECKPOINT_BACKEND`      | `memory` or `none`.                                                     |
| `AI_AGENT_RAG_SEARCH_MULTIPLIER`         | Over-fetch factor before type filtering.                                |
| `AI_AGENT_OTEL_*`                        | Toggle and endpoint for OTLP export.                                    |
| `AI_AGENT_MODEL_PROVIDER` / `MODEL_NAME` | Which chat model to load.                                               |

## Production Roadmap

Already in the template:

- API-key auth, rate limiting, request id propagation, body-size guard, error envelope.
- Pluggable checkpointer.
- Idempotent RAG ingestion, reranker hook.
- OTEL spans on agent and RAG operations.
- Eval harness with golden set.

Worth adding when you ship for real:

- Tenant-aware request context and audit metadata.
- Quota / spend enforcement on top of the rate limit.
- Tool sandboxing and allowlists once you bind tools.
- Human-in-the-loop interrupts for risky actions.
- Model routing and fallback policies.
- Prompt/version registry.
- Retrieval evaluation (recall, faithfulness, citation quality).
- Durable checkpointer backend (Postgres/Redis) for multi-replica memory.
- Secrets via a real secrets manager, not `.env`.

## Suggested Persistence Choices

- Postgres for durable checkpoints, audit logs, and business data.
- Redis for short-lived coordination, locks, and rate limiting (replaces the in-process limiter when you scale out).
- Object storage for large artifacts generated or consumed by agents.

## Deployment Notes

Run the API behind a real ingress with TLS, request-size limits, and timeout policies. Keep model API keys in a secrets manager. The in-process rate limiter is per-replica — put a global limiter at the ingress (or Redis-backed in-app) before scaling out.
