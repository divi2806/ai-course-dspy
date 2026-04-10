"""Raw text ingestion."""

from app.core.config import get_settings
from app.models.schemas import IngestedContent
from app.utils.chunker import chunk_text

settings = get_settings()


def ingest_text(text: str, title: str | None = None) -> IngestedContent:
    """
    Chunk raw text and return ingested content.

    Args:
        text:  Raw text to ingest (minimum 50 chars enforced by the schema).
        title: Optional document title.

    Raises:
        ValueError: If text is empty after stripping whitespace.
    """
    text = text.strip()
    if not text:
        raise ValueError("Cannot ingest empty text.")

    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)

    return IngestedContent(
        source_type="text",
        source_ref="raw",
        title=title or "Untitled Document",
        chunks=chunks,
    )
