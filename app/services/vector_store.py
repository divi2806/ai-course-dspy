"""ChromaDB-backed vector store for document chunks."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    import chromadb

log = logging.getLogger(__name__)
settings = get_settings()


@lru_cache(maxsize=1)
def _get_client() -> "chromadb.ClientAPI":
    import chromadb

    return chromadb.PersistentClient(path=settings.chroma_persist_dir)


@lru_cache(maxsize=1)
def _get_embedding_fn():
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    return SentenceTransformerEmbeddingFunction(
        model_name=settings.embedding_model
    )


def _collection():
    client = _get_client()
    return client.get_or_create_collection(
        name="document_chunks",
        embedding_function=_get_embedding_fn(),
        metadata={"hnsw:space": "cosine"},
    )


class VectorStore:
    """Thin wrapper around a ChromaDB collection."""

    def add_chunks(self, document_id: str, chunks: list[str]) -> None:
        """Embed and persist *chunks* keyed by *document_id*."""
        if not chunks:
            return
        collection = _collection()
        ids = [f"{document_id}::{i}" for i in range(len(chunks))]
        metadatas = [{"document_id": document_id, "chunk_index": i} for i in range(len(chunks))]
        collection.add(documents=chunks, ids=ids, metadatas=metadatas)
        log.info("Stored %d chunks for document %s", len(chunks), document_id)

    def get_chunks(self, document_id: str) -> list[str]:
        """Retrieve all chunks for a document in their original order."""
        collection = _collection()
        results = collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
        )
        if not results["documents"]:
            return []
        # Sort by chunk_index to restore order
        paired = zip(results["documents"], results["metadatas"])
        sorted_pairs = sorted(paired, key=lambda p: p[1].get("chunk_index", 0))
        return [doc for doc, _ in sorted_pairs]

    def search(
        self,
        document_id: str,
        query: str,
        n_results: int = 10,
    ) -> list[str]:
        """Semantic search within a document's chunks."""
        collection = _collection()
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"document_id": document_id},
            include=["documents"],
        )
        docs = results.get("documents", [[]])[0]
        return docs

    def delete_document(self, document_id: str) -> None:
        """Remove all chunks belonging to a document."""
        collection = _collection()
        collection.delete(where={"document_id": document_id})
        log.info("Deleted chunks for document %s", document_id)


# Module-level singleton
vector_store = VectorStore()
