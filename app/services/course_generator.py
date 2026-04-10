import json
import logging
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Course, Document
from app.models.schemas import CourseResponse, Module
from app.services.pipeline.rlm_pipeline import run_rlm

log = logging.getLogger(__name__)


def _parse_modules(modules_data: list[dict]) -> list[Module]:
    result: list[Module] = []
    for item in modules_data:
        try:
            # LLMs sometimes use alternate field names — try all known variants
            explanation = (
                item.get("explanation")
                or item.get("detailed_explanation")
                or item.get("content")
                or item.get("description")
                or ""
            )
            examples = (
                item.get("examples")
                or item.get("example_list")
                or []
            )
            result.append(
                Module(
                    title=item.get("title", "Untitled Module"),
                    explanation=explanation,
                    examples=examples,
                    code_snippets=item.get("code_snippets", []),
                    key_takeaways=item.get("key_takeaways", []),
                )
            )
        except Exception as exc:
            log.warning("Skipping malformed module: %s", exc)
    return result


async def generate_course(
    document_id: str,
    difficulty: Literal["easy", "medium", "hard"],
    db: AsyncSession,
) -> CourseResponse:
    result = await db.execute(select(Document).where(Document.id == document_id))
    document: Document | None = result.scalar_one_or_none()
    if document is None:
        raise ValueError(f"Document not found: {document_id}")

    if not document.content:
        raise ValueError(f"No content found for document {document_id}. Re-ingest the document.")

    log.info("Running RLM on document %s (difficulty=%s)", document_id, difficulty)

    raw_course = run_rlm(document_text=document.content, difficulty=difficulty)

    title = raw_course.get("title") or f"{document.title or 'Course'} ({difficulty})"
    summary = raw_course.get("summary") or ""
    modules = _parse_modules(raw_course.get("modules") or [])

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
