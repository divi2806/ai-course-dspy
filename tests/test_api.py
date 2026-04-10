from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestingSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


SAMPLE_TEXT = (
    "Python is a high-level programming language. "
    "It supports object-oriented, procedural, and functional programming. "
    "Recursion is a method where a function calls itself to solve sub-problems. "
    "Dynamic programming breaks problems into overlapping sub-problems. "
) * 15

SAMPLE_COURSE = {
    "title": "Python Fundamentals",
    "summary": "Core concepts of Python for beginners.",
    "modules": [
        {
            "title": "Variables and Types",
            "explanation": "Python uses dynamic typing.",
            "examples": ["x = 42"],
            "code_snippets": ["x: int = 42"],
            "key_takeaways": ["Python is dynamically typed."],
        }
    ],
}


def _mock_rlm(course_data: dict):
    mock_rlm = MagicMock()
    mock_rlm.return_value = course_data
    return patch("app.services.course_generator.run_rlm", return_value=course_data)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_text_success(client: AsyncClient):
    resp = await client.post("/ingest/text", json={"text": SAMPLE_TEXT, "title": "Test Doc"})
    assert resp.status_code == 201
    data = resp.json()
    assert "document_id" in data
    assert data["source_type"] == "text"
    assert data["word_count"] > 0
    assert data["title"] == "Test Doc"


@pytest.mark.asyncio
async def test_ingest_text_too_short(client: AsyncClient):
    resp = await client.post("/ingest/text", json={"text": "too short"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_text_empty(client: AsyncClient):
    resp = await client.post("/ingest/text", json={"text": "   " * 20})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ingest_pdf_wrong_extension(client: AsyncClient):
    resp = await client.post(
        "/ingest/pdf",
        files={"file": ("document.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_pdf_success(client: AsyncClient, tmp_path):
    pytest.importorskip("fitz", reason="PyMuPDF not installed")
    import fitz

    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), SAMPLE_TEXT[:2000])
    doc.save(str(pdf_path))
    doc.close()

    with open(pdf_path, "rb") as f:
        resp = await client.post(
            "/ingest/pdf",
            files={"file": ("test.pdf", f, "application/pdf")},
        )
    assert resp.status_code == 201
    assert resp.json()["source_type"] == "pdf"


# ---------------------------------------------------------------------------
# Course generation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_course_success(client: AsyncClient):
    ingest_resp = await client.post(
        "/ingest/text", json={"text": SAMPLE_TEXT, "title": "Python 101"}
    )
    assert ingest_resp.status_code == 201
    doc_id = ingest_resp.json()["document_id"]

    with _mock_rlm(SAMPLE_COURSE):
        resp = await client.post(
            "/generate-course",
            json={"document_id": doc_id, "difficulty": "easy"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["document_id"] == doc_id
    assert data["difficulty"] == "easy"
    assert data["title"] == "Python Fundamentals"
    assert len(data["modules"]) == 1
    assert "course_id" in data


@pytest.mark.asyncio
async def test_generate_course_unknown_document(client: AsyncClient):
    with _mock_rlm(SAMPLE_COURSE):
        resp = await client.post(
            "/generate-course",
            json={"document_id": "non-existent-id", "difficulty": "medium"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_course_invalid_difficulty(client: AsyncClient):
    resp = await client.post(
        "/generate-course",
        json={"document_id": "some-id", "difficulty": "expert"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Get course
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_course_success(client: AsyncClient):
    ingest_resp = await client.post(
        "/ingest/text", json={"text": SAMPLE_TEXT, "title": "Retrieve Test"}
    )
    doc_id = ingest_resp.json()["document_id"]

    with _mock_rlm(SAMPLE_COURSE):
        gen_resp = await client.post(
            "/generate-course",
            json={"document_id": doc_id, "difficulty": "hard"},
        )
    course_id = gen_resp.json()["course_id"]

    resp = await client.get(f"/course/{course_id}")
    assert resp.status_code == 200
    assert resp.json()["course_id"] == course_id


@pytest.mark.asyncio
async def test_get_course_not_found(client: AsyncClient):
    resp = await client.get("/course/does-not-exist")
    assert resp.status_code == 404
