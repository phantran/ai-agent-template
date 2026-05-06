from collections.abc import Sequence

from langchain_core.documents import Document

from ai_agent_template.core.settings import Settings
from ai_agent_template.rag.schemas import RagSource
from ai_agent_template.rag.service import RagService


class FakeVectorStore:
    def __init__(self) -> None:
        self.documents: list[Document] = []
        self._ids: list[str] = []
        self.add_calls: int = 0

    def add_documents(self, documents: list[Document], **kwargs: object) -> None:
        self.add_calls += 1
        ids = kwargs.get("ids")
        if not isinstance(ids, list):
            self.documents.extend(documents)
            return
        # Emulate qdrant upsert-by-id semantics.
        existing = dict(zip(self._ids, self.documents, strict=False))
        existing.update(dict(zip([str(v) for v in ids], documents, strict=False)))
        self._ids = list(existing.keys())
        self.documents = list(existing.values())

    def similarity_search_with_score(self, query: str, k: int = 4) -> list[tuple[Document, float]]:
        return [(document, 0.8) for document in self.documents[:k]]


def test_rag_service_ingests_and_searches_chunks() -> None:
    settings = Settings(rag_chunk_size=20, rag_chunk_overlap=5)
    vector_store = FakeVectorStore()
    service = RagService(settings=settings, vector_store=vector_store)

    response = service.ingest_text(
        text="Alpha agents need observability. Beta agents need evals.",
        source="notes.md",
        document_type="knowledge",
        metadata={"kind": "note"},
    )
    sources = service.search("observability")

    assert response.source == "notes.md"
    assert response.chunks >= 1
    assert sources[0].source == "notes.md"
    assert sources[0].metadata == {"document_type": "knowledge", "kind": "note"}


def test_rag_service_separates_voice_samples() -> None:
    settings = Settings(rag_chunk_size=100, rag_chunk_overlap=0)
    vector_store = FakeVectorStore()
    service = RagService(settings=settings, vector_store=vector_store)

    service.ingest_text(text="Factual deployment note.", source="facts", document_type="knowledge")
    service.ingest_text(
        text="I tend to write with short sentences and practical warmth.",
        source="journal",
        document_type="voice_sample",
    )

    assert [source.source for source in service.search("write")] == ["facts"]
    assert [source.source for source in service.search_voice("write")] == ["journal"]


def test_rag_ingest_is_idempotent_for_identical_text() -> None:
    settings = Settings(rag_chunk_size=200, rag_chunk_overlap=0)
    vector_store = FakeVectorStore()
    service = RagService(settings=settings, vector_store=vector_store)

    text = "Stable content yields stable chunk IDs."
    first = service.ingest_text(text=text, source="notes", document_type="knowledge")
    second = service.ingest_text(text=text, source="notes", document_type="knowledge")

    assert first.chunks == second.chunks
    assert vector_store.add_calls == 2
    assert len(vector_store.documents) == first.chunks  # Upsert, not duplicate.


def test_rag_reranker_hook_receives_results() -> None:
    settings = Settings(rag_chunk_size=200, rag_chunk_overlap=0)
    vector_store = FakeVectorStore()

    captured: dict[str, object] = {}

    class ReverseReranker:
        def rerank(self, query: str, sources: Sequence[RagSource]) -> list[RagSource]:
            captured["query"] = query
            captured["count"] = len(sources)
            return list(reversed(list(sources)))

    service = RagService(settings=settings, vector_store=vector_store, reranker=ReverseReranker())
    service.ingest_text(text="alpha", source="a", document_type="knowledge")
    service.ingest_text(text="beta", source="b", document_type="knowledge")

    results = service.search("anything")

    assert captured["query"] == "anything"
    assert captured["count"] == 2
    assert [source.source for source in results] == ["b", "a"]
