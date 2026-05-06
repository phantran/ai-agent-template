from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from ai_agent_template.core.settings import Settings


def build_embeddings(settings: Settings) -> Embeddings:
    return FastEmbedEmbeddings(model_name=settings.rag_embedding_model_name)


def build_qdrant_client(settings: Settings) -> QdrantClient:
    if settings.qdrant_url:
        return QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        )
    return QdrantClient(path=settings.qdrant_storage_path)


def ensure_collection(client: QdrantClient, settings: Settings) -> None:
    if client.collection_exists(settings.rag_collection_name):
        return

    client.create_collection(
        collection_name=settings.rag_collection_name,
        vectors_config=VectorParams(
            size=settings.rag_embedding_dimensions,
            distance=Distance.COSINE,
        ),
    )


def build_vector_store(settings: Settings) -> QdrantVectorStore:
    client = build_qdrant_client(settings)
    ensure_collection(client, settings)
    return QdrantVectorStore(
        client=client,
        collection_name=settings.rag_collection_name,
        embedding=build_embeddings(settings),
        retrieval_mode=RetrievalMode.DENSE,
    )
