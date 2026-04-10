from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class IngestTextRequest(BaseModel):
    text: str = Field(..., min_length=50, description="Raw text content to ingest")
    title: str | None = Field(None, description="Optional document title")


class IngestYouTubeRequest(BaseModel):
    url: str = Field(..., description="YouTube video or playlist URL")
    title: str | None = Field(None, description="Optional title override")


class IngestResponse(BaseModel):
    document_id: str
    source_type: str
    title: str | None
    word_count: int
    message: str


# ---------------------------------------------------------------------------
# Course Generation
# ---------------------------------------------------------------------------

class GenerateCourseRequest(BaseModel):
    document_id: str = Field(..., description="ID returned from /ingest")
    difficulty: Literal["easy", "medium", "hard"] = Field(
        ..., description="Target difficulty level"
    )


class Module(BaseModel):
    title: str
    explanation: str
    examples: list[str] = Field(default_factory=list)
    code_snippets: list[str] = Field(default_factory=list)
    key_takeaways: list[str] = Field(default_factory=list)


class CourseResponse(BaseModel):
    course_id: str
    document_id: str
    difficulty: Literal["easy", "medium", "hard"]
    title: str
    summary: str
    modules: list[Module]
    created_at: datetime


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

class IngestedContent(BaseModel):
    source_type: Literal["pdf", "text", "youtube_video", "youtube_playlist"]
    source_ref: str
    title: str | None
    full_text: str
