"""Course generation and retrieval endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import CourseResponse, GenerateCourseRequest
from app.services.course_generator import generate_course, get_course

log = logging.getLogger(__name__)
router = APIRouter(tags=["Courses"])


@router.post(
    "/generate-course",
    response_model=CourseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_course_endpoint(
    body: GenerateCourseRequest,
    db: AsyncSession = Depends(get_db),
) -> CourseResponse:
    """
    Run the DSPy pipeline and generate a difficulty-specific course for an
    ingested document.
    """
    try:
        return await generate_course(
            document_id=body.document_id,
            difficulty=body.difficulty,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        log.exception("Course generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Course generation failed: {exc}",
        )


@router.get("/course/{course_id}", response_model=CourseResponse)
async def get_course_endpoint(
    course_id: str,
    db: AsyncSession = Depends(get_db),
) -> CourseResponse:
    """Retrieve a previously generated course by its ID."""
    try:
        return await get_course(course_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
