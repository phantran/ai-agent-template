# Architecture Diagrams

## System Overview

```mermaid
flowchart LR
    User["User"] --> Frontend["React/Vite Console"]
    Frontend -->|"HTTP JSON / multipart / SSE"| Edge

    subgraph Edge["API Edge"]
        CORS["CORS"]
        RateLimit["Rate Limit"]
        BodyLimit["Body Size Guard"]
        ReqCtx["Request ID + Logs"]
        Auth["API Key Auth"]
        Errors["Error Envelope"]
    end

    Edge --> AgentService["AgentService\n(invoke / stream)"]
    AgentService --> Graph["LangGraph Workflow"]
    AgentService -->|"thread_id"| Checkpointer["Checkpointer\n(memory | none)"]

    Graph --> Retriever["Retrieve Node"]
    Retriever --> RagService["RagService"]
    RagService --> Qdrant["Qdrant Vector DB"]
    RagService --> Embeddings["FastEmbed Embeddings"]
    RagService -.optional.-> Reranker["Reranker"]

    Graph --> ModelNode["Model Node"]
    ModelNode --> Provider{"Model Provider"}
    Provider --> Groq["Groq"]
    Provider --> OpenAI["OpenAI"]

    AgentService -.spans.-> OTEL["OTLP Collector"]
    RagService -.spans.-> OTEL
```

## Synchronous Invocation

```mermaid
sequenceDiagram
    actor User
    participant UI as React Console
    participant Edge as API Edge
    participant Service as AgentService
    participant Graph as LangGraph
    participant RAG as RagService
    participant DB as Qdrant
    participant LLM as Groq/OpenAI

    User->>UI: Sends prompt
    UI->>Edge: POST /v1/agent/invoke (x-api-key, x-request-id?)
    Edge->>Edge: rate limit + body size + request id
    Edge->>Edge: validate API key
    Edge->>Service: AgentInvokeRequest
    Service->>Service: open agent.invoke span
    Service->>Graph: ainvoke(initial_state, thread_id)
    Graph->>RAG: search(query) [knowledge]
    RAG->>DB: similarity_search_with_score
    DB-->>RAG: candidates
    RAG-->>Graph: top_k sources
    Graph->>RAG: search_voice(query)
    RAG-->>Graph: top_k voice samples
    Graph->>LLM: system + context + voice + history
    LLM-->>Graph: assistant message
    Graph-->>Service: state with messages + sources
    Service-->>Edge: AgentInvokeResponse
    Edge-->>UI: 200 + x-request-id
```

## Streaming Invocation

```mermaid
sequenceDiagram
    actor User
    participant UI as React Console
    participant Edge as API Edge
    participant Service as AgentService
    participant Graph as LangGraph
    participant LLM as Groq/OpenAI

    User->>UI: Sends prompt
    UI->>Edge: POST /v1/agent/stream
    Edge->>Service: AgentInvokeRequest
    Service->>Graph: astream(stream_mode=["updates","messages"])
    Graph-->>Service: updates: retrieve.sources
    Service-->>UI: event: sources
    Graph->>LLM: prompt
    loop for each token chunk
        LLM-->>Graph: AIMessageChunk
        Graph-->>Service: messages: chunk
        Service-->>UI: event: delta
    end
    Service-->>UI: event: done
    Note over UI: incremental render of tokens<br/>and source badges
```

## Error Path

```mermaid
flowchart LR
    Request["Incoming request"] --> Edge["API Edge middleware"]
    Edge -->|"429"| RateLimited["Rate-limited response\n(Retry-After, X-RateLimit-*)"]
    Edge -->|"413"| TooLarge["Body too large"]
    Edge --> Auth{"Auth required?"}
    Auth -->|"missing/invalid key"| Unauthorized["401 envelope"]
    Auth -->|"ok"| Route["Route handler"]
    Route -->|"validation failure"| Validation["422 envelope\n(errors[])"]
    Route -->|"raised HTTPException"| Mapped["Mapped envelope"]
    Route -->|"unhandled exception"| Unhandled["500 envelope\n(logged with stack)"]
    Validation --> Response["JSON: type, title, status, detail, request_id"]
    Mapped --> Response
    Unhandled --> Response
    Unauthorized --> Response
    RateLimited --> Response
    TooLarge --> Response
```

## RAG Ingestion

```mermaid
flowchart TD
    Upload["Paste text or upload file"] --> Endpoint{"Endpoint"}

    Endpoint -->|"Knowledge"| KnowledgeAPI["POST /v1/rag/documents or /v1/rag/files"]
    Endpoint -->|"Voice sample"| VoiceAPI["POST /v1/rag/voice-samples or /v1/rag/voice-files"]

    KnowledgeAPI --> Loader["Text/PDF Loader"]
    VoiceAPI --> Loader

    Loader --> Splitter["RecursiveCharacterTextSplitter"]
    Splitter --> ChunkId["Stable UUIDv5 id\n(source + type + sha256(content))"]
    ChunkId --> Embedder["FastEmbedEmbeddings"]
    Embedder --> Store["QdrantVectorStore\n(upsert by id = idempotent)"]

    Store --> Metadata{"Metadata"}
    Metadata --> KnowledgeType["document_type=knowledge"]
    Metadata --> VoiceType["document_type=voice_sample"]

    KnowledgeType --> Collection["Qdrant collection: agent_knowledge"]
    VoiceType --> Collection
```

## RAG Retrieval

```mermaid
flowchart LR
    Query["query"] --> Service["RagService.search(query)"]
    Service --> Fetch["similarity_search_with_score\nk = top_k * search_multiplier"]
    Fetch --> Filter["filter by document_type"]
    Filter --> Threshold["score >= rag_score_threshold"]
    Threshold --> TopK["take top_k"]
    TopK --> Rerank{"reranker?"}
    Rerank -->|"yes"| Rerank2["Reranker.rerank(query, sources)"]
    Rerank -->|"no"| Out["RagSource[]"]
    Rerank2 --> Out
```

## Docker Compose Topology

```mermaid
flowchart TB
    subgraph Compose["docker compose"]
        Frontend["frontend\nReact + Vite\n:5173"]
        API["api\nFastAPI\n:8000"]
        Qdrant["qdrant\nVector DB\n:6333 / :6334"]
        Volume[("qdrant_data volume")]
    end

    Browser["Browser"] -->|"http://127.0.0.1:5173"| Frontend
    Frontend -->|"VITE_API_BASE_URL\nVITE_API_KEY"| API
    API -->|"AI_AGENT_QDRANT_URL=http://qdrant:6333"| Qdrant
    Qdrant --> Volume
    API -->|"GROQ_API_KEY / OPENAI_API_KEY"| Providers["LLM providers"]
    API -.optional.-> OTEL["OTLP collector\n(AI_AGENT_OTEL_ENABLED=true)"]
```

## Source Types

```mermaid
classDiagram
    class RagSource {
        string source
        string content
        float score
        object metadata
    }

    class KnowledgeDocument {
        document_type = knowledge
        facts and reference material
    }

    class VoiceSample {
        document_type = voice_sample
        user-authored writing examples
    }

    RagSource <|-- KnowledgeDocument
    RagSource <|-- VoiceSample
```

## Configuration Snapshot

```mermaid
flowchart LR
    Env[".env / environment"] --> Settings["Settings\n(pydantic-settings)"]
    Settings --> Auth["auth_api_keys"]
    Settings --> RateLimit["rate_limit_*"]
    Settings --> Body["request_max_body_bytes"]
    Settings --> ReqId["request_id_header"]
    Settings --> Checkpoint["agent_checkpoint_backend"]
    Settings --> Model["model_provider / model_name"]
    Settings --> RAG["rag_*"]
    Settings --> OTEL["otel_*"]
    Settings --> CORS["cors_allowed_origins"]
```
