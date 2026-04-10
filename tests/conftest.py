"""Shared pytest configuration: silence noisy loggers, set env for tests."""

import os

import pytest

# Point to a test .env so settings don't need real keys
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_MODEL", "gpt-4o-mini")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("CHROMA_PERSIST_DIR", "/tmp/test_chroma")
os.environ.setdefault("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Patch vector_store.add_chunks globally so tests don't spin up ChromaDB
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_vector_store(monkeypatch):
    """Replace ChromaDB calls with in-memory stubs for all tests."""
    store: dict[str, list[str]] = {}

    def fake_add(document_id, chunks):
        store[document_id] = chunks

    def fake_get(document_id):
        return store.get(document_id, [])

    def fake_search(document_id, query, n_results=10):
        return store.get(document_id, [])[:n_results]

    def fake_delete(document_id):
        store.pop(document_id, None)

    monkeypatch.setattr("app.services.vector_store.vector_store.add_chunks", fake_add)
    monkeypatch.setattr("app.services.vector_store.vector_store.get_chunks", fake_get)
    monkeypatch.setattr("app.services.vector_store.vector_store.search", fake_search)
    monkeypatch.setattr("app.services.vector_store.vector_store.delete_document", fake_delete)

    # Also patch the import used inside ingest routes
    monkeypatch.setattr("app.api.routes.ingest.vector_store.add_chunks", fake_add)
    monkeypatch.setattr("app.services.course_generator.vector_store.get_chunks", fake_get)
