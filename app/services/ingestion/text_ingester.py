from app.models.schemas import IngestedContent


def ingest_text(text: str, title: str | None = None) -> IngestedContent:
    text = text.strip()
    if not text:
        raise ValueError("Cannot ingest empty text.")

    return IngestedContent(
        source_type="text",
        source_ref="raw",
        title=title or "Untitled Document",
        full_text=text,
    )
