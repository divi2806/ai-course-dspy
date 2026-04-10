"""Unit tests for ingestion services and chunker."""

import textwrap

import pytest

from app.services.ingestion.text_ingester import ingest_text
from app.utils.chunker import chunk_text


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------

class TestChunker:
    def test_basic_split(self):
        text = " ".join([f"word{i}" for i in range(600)])
        chunks = chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) > 1
        for chunk in chunks:
            words = chunk.split()
            assert len(words) <= 110  # allow small overshoot for sentence boundaries

    def test_overlap_carries_words(self):
        text = " ".join([f"word{i}" for i in range(300)])
        chunks = chunk_text(text, chunk_size=50, overlap=10)
        # Last words of chunk N should appear in chunk N+1
        assert len(chunks) >= 2
        tail_words = set(chunks[0].split()[-5:])
        head_words = set(chunks[1].split()[:15])
        assert tail_words & head_words  # some overlap

    def test_single_short_text(self):
        text = "This is a short sentence."
        chunks = chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) == 1
        assert chunks[0] == "This is a short sentence."

    def test_empty_text_returns_empty(self):
        assert chunk_text("", chunk_size=100, overlap=10) == []

    def test_very_long_single_sentence(self):
        # One huge sentence that exceeds chunk_size
        text = " ".join([f"tok{i}" for i in range(1000)])
        chunks = chunk_text(text, chunk_size=200, overlap=20)
        assert len(chunks) > 1


# ---------------------------------------------------------------------------
# Text ingester
# ---------------------------------------------------------------------------

class TestTextIngester:
    SAMPLE_TEXT = textwrap.dedent("""\
        Python is a versatile programming language. It supports multiple paradigms.
        Recursion is a technique where a function calls itself. It is used in many algorithms.
        Dynamic programming optimises recursive solutions by memoisation. It reduces time complexity.
        Graph traversal algorithms like BFS and DFS explore nodes. They are fundamental to CS.
    """) * 10  # repeat to exceed one chunk

    def test_returns_ingested_content(self):
        result = ingest_text(self.SAMPLE_TEXT, title="Test Doc")
        assert result.source_type == "text"
        assert result.title == "Test Doc"
        assert len(result.chunks) >= 1
        assert all(isinstance(c, str) for c in result.chunks)

    def test_default_title(self):
        result = ingest_text(self.SAMPLE_TEXT)
        assert result.title == "Untitled Document"

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="empty"):
            ingest_text("   ")

    def test_source_ref_is_raw(self):
        result = ingest_text(self.SAMPLE_TEXT)
        assert result.source_ref == "raw"

    def test_chunk_count_matches(self):
        result = ingest_text(self.SAMPLE_TEXT)
        assert len(result.chunks) == len([c for c in result.chunks if c])


# ---------------------------------------------------------------------------
# PDF ingester (mocked file system)
# ---------------------------------------------------------------------------

class TestPdfIngester:
    def test_missing_file_raises(self, tmp_path):
        from app.services.ingestion.pdf_ingester import ingest_pdf
        with pytest.raises(FileNotFoundError):
            ingest_pdf(tmp_path / "nonexistent.pdf")

    def test_valid_pdf(self, tmp_path):
        """Create a minimal PDF and ingest it."""
        pytest.importorskip("fitz", reason="PyMuPDF not installed")
        import fitz

        pdf_path = tmp_path / "sample.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello World. " * 100)
        doc.save(str(pdf_path))
        doc.close()

        from app.services.ingestion.pdf_ingester import ingest_pdf
        result = ingest_pdf(pdf_path, title="Sample PDF")
        assert result.source_type == "pdf"
        assert result.title == "Sample PDF"
        assert len(result.chunks) >= 1
