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


# ---------------------------------------------------------------------------
# Topic ingestion
# ---------------------------------------------------------------------------

SAMPLE_INGESTED_CONTENT = {
    "source_type": "text",
    "source_ref": "perplexity:sonar-pro:Transformers",
    "title": "Research Report: Transformers",
    "full_text": "Transformers are a deep learning architecture. " * 60,
}


@pytest.mark.asyncio
async def test_ingest_topic_no_api_key(client: AsyncClient):
    """Returns 503 when PERPLEXITY_API_KEY is not set."""
    with patch("app.api.routes.ingest.settings") as mock_settings:
        mock_settings.perplexity_api_key = None
        resp = await client.post(
            "/ingest/topic",
            json={"topic": "Transformer architecture"},
        )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_ingest_topic_success(client: AsyncClient):
    """Happy-path: mocked Perplexity call returns a document_id."""
    from app.models.schemas import IngestedContent

    fake_content = IngestedContent(**SAMPLE_INGESTED_CONTENT)
    fake_citations = ["https://arxiv.org/abs/1706.03762"]

    with (
        patch("app.api.routes.ingest.settings") as mock_settings,
        patch(
            "app.api.routes.ingest.ingest_topic",
            return_value=(fake_content, fake_citations),
        ),
    ):
        mock_settings.perplexity_api_key = "pplx-test-key"
        resp = await client.post(
            "/ingest/topic",
            json={
                "topic": "Transformer architecture",
                "details": "Focus on self-attention",
                "focus_areas": ["attention", "positional encoding"],
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert "document_id" in data
    assert data["title"] == "Research Report: Transformers"
    assert data["sources"] == fake_citations
    assert data["word_count"] > 0


@pytest.mark.asyncio
async def test_ingest_topic_api_error(client: AsyncClient):
    """Perplexity API failure is surfaced as 502."""
    with (
        patch("app.api.routes.ingest.settings") as mock_settings,
        patch(
            "app.api.routes.ingest.ingest_topic",
            side_effect=RuntimeError("Perplexity API error 429: rate limited"),
        ),
    ):
        mock_settings.perplexity_api_key = "pplx-test-key"
        resp = await client.post(
            "/ingest/topic",
            json={"topic": "Transformer architecture"},
        )
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Evaluation (MCQ generation)
# ---------------------------------------------------------------------------

SAMPLE_MCQ_QUESTIONS = [
    {
        "situation": "A student is learning about dynamic typing in Python.",
        "task": "Which of the following best describes how Python handles variable types?",
        "options": {
            "A": "Types are declared at compile time.",
            "B": "Types are inferred at runtime and can change.",
            "C": "Every variable must have a type annotation.",
            "D": "Python uses static typing by default.",
        },
        "correct_answer": "B",
        "result": "Python is dynamically typed — variables do not need type declarations.",
    }
]


def _mock_mcq_generator(questions: list[dict]):
    """Patch the ChainOfThought MCQ generator to return fixed questions."""
    import json

    mock_pred = MagicMock()
    mock_pred.questions_json = json.dumps(questions)
    return patch(
        "app.services.evaluation_generator._mcq_generator",
        return_value=mock_pred,
    )


async def _create_course(client: AsyncClient) -> str:
    """Helper: ingest text and generate a course; return course_id."""
    ingest_resp = await client.post(
        "/ingest/text", json={"text": SAMPLE_TEXT, "title": "Eval Test Doc"}
    )
    assert ingest_resp.status_code == 201
    doc_id = ingest_resp.json()["document_id"]

    with _mock_rlm(SAMPLE_COURSE):
        gen_resp = await client.post(
            "/generate-course",
            json={"document_id": doc_id, "difficulty": "easy"},
        )
    assert gen_resp.status_code == 201
    return gen_resp.json()["course_id"]


@pytest.mark.asyncio
async def test_evaluate_success(client: AsyncClient):
    """POST /evaluate generates MCQ questions for a valid course."""
    course_id = await _create_course(client)

    with _mock_mcq_generator(SAMPLE_MCQ_QUESTIONS):
        resp = await client.post("/evaluate", json={"course_id": course_id})

    assert resp.status_code == 201
    data = resp.json()
    assert data["course_id"] == course_id
    assert "evaluation_id" in data
    assert data["total_questions"] == 1
    q = data["questions"][0]
    assert q["correct_answer"] == "B"
    assert q["module_title"] == "Variables and Types"


@pytest.mark.asyncio
async def test_evaluate_course_not_found(client: AsyncClient):
    """POST /evaluate returns 404 for an unknown course_id."""
    resp = await client.post("/evaluate", json={"course_id": "does-not-exist"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_evaluation_success(client: AsyncClient):
    """GET /evaluate/{id} retrieves a previously generated evaluation."""
    course_id = await _create_course(client)

    with _mock_mcq_generator(SAMPLE_MCQ_QUESTIONS):
        post_resp = await client.post("/evaluate", json={"course_id": course_id})
    assert post_resp.status_code == 201
    evaluation_id = post_resp.json()["evaluation_id"]

    get_resp = await client.get(f"/evaluate/{evaluation_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["evaluation_id"] == evaluation_id
    assert data["course_id"] == course_id
    assert data["total_questions"] == 1


@pytest.mark.asyncio
async def test_get_evaluation_not_found(client: AsyncClient):
    """GET /evaluate/{id} returns 404 for an unknown evaluation_id."""
    resp = await client.get("/evaluate/does-not-exist")
    assert resp.status_code == 404
