import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.db import Document
from app.models.schemas import (
    IngestResponse,
    IngestTextRequest,
    IngestYouTubeRequest,
    IngestTopicRequest,
    TopicIngestResponse,
)
from app.services.ingestion import ingest_pdf, ingest_text, ingest_topic, ingest_youtube

log = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["Ingestion"])
settings = get_settings()


async def _persist(content, db: AsyncSession) -> Document:
    doc = Document(
        source_type=content.source_type,
        source_ref=content.source_ref,
        title=content.title,
        content=content.full_text,
    )
    db.add(doc)
    await db.flush()
    return doc


@router.post("/pdf", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_pdf_endpoint(
    file: UploadFile = File(..., description="PDF file to ingest"),
    title: str | None = Form(None, description="Optional document title"),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """Upload and ingest a PDF file."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only PDF files are accepted.",
        )

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        content = ingest_pdf(tmp_path, title=title or file.filename)
    except (ValueError, ImportError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    doc = await _persist(content, db)
    return IngestResponse(
        document_id=doc.id,
        source_type=doc.source_type,
        title=doc.title,
        word_count=len(doc.content.split()),
        message="PDF ingested successfully.",
    )


@router.post("/text", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_text_endpoint(
    body: IngestTextRequest,
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """Ingest raw text content."""
    try:
        content = ingest_text(body.text, title=body.title)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    doc = await _persist(content, db)
    return IngestResponse(
        document_id=doc.id,
        source_type=doc.source_type,
        title=doc.title,
        word_count=len(doc.content.split()),
        message="Text ingested successfully.",
    )


@router.post("/youtube", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_youtube_endpoint(
    body: IngestYouTubeRequest,
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """Ingest a YouTube video or playlist URL."""
    try:
        content = ingest_youtube(body.url, title=body.title)
    except (ImportError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    doc = await _persist(content, db)
    return IngestResponse(
        document_id=doc.id,
        source_type=doc.source_type,
        title=doc.title,
        word_count=len(doc.content.split()),
        message="YouTube content ingested successfully.",
    )


@router.post("/topic", response_model=TopicIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_topic_endpoint(
    body: IngestTopicRequest,
    db: AsyncSession = Depends(get_db),
) -> TopicIngestResponse:
    """
    Research a topic using Perplexity and store the report as a document.
    Returns a document_id you can immediately pass to /generate-course.
    No existing material needed — just describe what you want to learn.
    """
    if not settings.perplexity_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PERPLEXITY_API_KEY is not configured.",
        )

    try:
        content, citations = await ingest_topic(
            topic=body.topic,
            api_key=settings.perplexity_api_key,
            details=body.details,
            focus_areas=body.focus_areas,
            title=body.title,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    doc = await _persist(content, db)
    preview = doc.content[:500] + ("..." if len(doc.content) > 500 else "")

    return TopicIngestResponse(
        document_id=doc.id,
        title=doc.title or body.topic,
        word_count=len(doc.content.split()),
        sources=citations,
        report_preview=preview,
        message=f"Research complete. {len(citations)} sources found. Use document_id with /generate-course.",
    )
