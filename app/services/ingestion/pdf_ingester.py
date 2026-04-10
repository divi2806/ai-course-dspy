from pathlib import Path

from app.models.schemas import IngestedContent


def ingest_pdf(file_path: str | Path, title: str | None = None) -> IngestedContent:
    try:
        import fitz
    except ImportError as exc:
        raise ImportError(
            "PyMuPDF is required for PDF ingestion. Install it with: pip install pymupdf"
        ) from exc

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    pages: list[str] = []
    with fitz.open(str(file_path)) as doc:
        for page in doc:
            text = page.get_text("text")
            if text.strip():
                pages.append(text)

    if not pages:
        raise ValueError(f"No extractable text found in PDF: {file_path.name}")

    return IngestedContent(
        source_type="pdf",
        source_ref=str(file_path),
        title=title or file_path.stem,
        full_text="\n\n".join(pages),
    )
