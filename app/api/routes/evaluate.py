"""Evaluation (MCQ generation) endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import EvaluateRequest, EvaluationResponse
from app.services.evaluation_generator import generate_evaluation, get_evaluation

log = logging.getLogger(__name__)
router = APIRouter(tags=["Evaluation"])


@router.post(
    "/evaluate",
    response_model=EvaluationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def evaluate_endpoint(
    body: EvaluateRequest,
    db: AsyncSession = Depends(get_db),
) -> EvaluationResponse:
    """
    Generate MCQ questions covering all modules of a course.
    Questions scale with module count — 2-4 per module — to cover the full course.
    """
    try:
        return await generate_evaluation(course_id=body.course_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        log.exception("Evaluation generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation generation failed: {exc}",
        )


@router.get("/evaluate/{evaluation_id}", response_model=EvaluationResponse)
async def get_evaluation_endpoint(
    evaluation_id: str,
    db: AsyncSession = Depends(get_db),
) -> EvaluationResponse:
    """Retrieve a previously generated evaluation by its ID."""
    try:
        return await get_evaluation(evaluation_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
