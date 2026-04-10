import json
import logging
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Course, Document
from app.models.schemas import CourseResponse, Module
from app.services.pipeline.course_pipeline import get_pipeline, parse_modules
from app.services.vector_store import vector_store

log = logging.getLogger(__name__)


async def generate_course(
    document_id: str,
    difficulty: Literal["easy", "medium", "hard"],
    db: AsyncSession,
) -> CourseResponse:
    result = await db.execute(select(Document).where(Document.id == document_id))
    document: Document | None = result.scalar_one_or_none()
    if document is None:
        raise ValueError(f"Document not found: {document_id}")

    chunks = vector_store.get_chunks(document_id)
    if not chunks:
        raise ValueError(f"No chunks found for document {document_id}. Re-ingest the document.")

    log.info("Running pipeline on document %s (%d chunks, difficulty=%s)", document_id, len(chunks), difficulty)

    raw_course = get_pipeline()(text="\n\n".join(chunks), difficulty=difficulty)

    title = raw_course.get("title") or f"{document.title or 'Course'} ({difficulty})"
    summary = raw_course.get("summary") or ""
    modules: list[Module] = parse_modules(raw_course.get("modules") or [])

    course = Course(
        document_id=document_id,
        difficulty=difficulty,
        title=title,
        summary=summary,
        modules_json=json.dumps([m.model_dump() for m in modules]),
    )
    db.add(course)
    await db.flush()

    log.info("Course %s created for document %s", course.id, document_id)

    return CourseResponse(
        course_id=course.id,
        document_id=document_id,
        difficulty=difficulty,
        title=title,
        summary=summary,
        modules=modules,
        created_at=course.created_at,
    )


async def get_course(course_id: str, db: AsyncSession) -> CourseResponse:
    result = await db.execute(select(Course).where(Course.id == course_id))
    course: Course | None = result.scalar_one_or_none()
    if course is None:
        raise ValueError(f"Course not found: {course_id}")

    modules = [Module(**m) for m in json.loads(course.modules_json)]

    return CourseResponse(
        course_id=course.id,
        document_id=course.document_id,
        difficulty=course.difficulty,
        title=course.title,
        summary=course.summary,
        modules=modules,
        created_at=course.created_at,
    )
