"""PDF ingestion using PyMuPDF (fitz)."""

from pathlib import Path

from app.core.config import get_settings
from app.models.schemas import IngestedContent
from app.utils.chunker import chunk_text

settings = get_settings()


def ingest_pdf(file_path: str | Path, title: str | None = None) -> IngestedContent:
    """
    Extract text from a PDF file and return chunked content.

    Args:
        file_path: Path to the PDF file on disk.
        title:     Optional title override; defaults to the file stem.

    Raises:
        ImportError:  If PyMuPDF is not installed.
        FileNotFoundError: If the PDF path doesn't exist.
        ValueError:   If the PDF contains no extractable text.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise ImportError(
            "PyMuPDF is required for PDF ingestion. Install it with: pip install pymupdf"
        ) from exc

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    raw_pages: list[str] = []
    with fitz.open(str(file_path)) as doc:
        for page in doc:
            text = page.get_text("text")
            if text.strip():
                raw_pages.append(text)

    if not raw_pages:
        raise ValueError(f"No extractable text found in PDF: {file_path.name}")

    full_text = "\n\n".join(raw_pages)
    chunks = chunk_text(full_text, settings.chunk_size, settings.chunk_overlap)

    return IngestedContent(
        source_type="pdf",
        source_ref=str(file_path),
        title=title or file_path.stem,
        chunks=chunks,
    )
