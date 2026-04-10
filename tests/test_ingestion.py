import pytest

from app.services.ingestion.text_ingester import ingest_text


class TestTextIngester:
    SAMPLE_TEXT = (
        "Python is a versatile programming language. It supports multiple paradigms. "
        "Recursion is a technique where a function calls itself. "
        "Dynamic programming optimises recursive solutions by memoisation. "
        "Graph traversal algorithms like BFS and DFS explore nodes. "
    ) * 10

    def test_returns_ingested_content(self):
        result = ingest_text(self.SAMPLE_TEXT, title="Test Doc")
        assert result.source_type == "text"
        assert result.title == "Test Doc"
        assert len(result.full_text) > 0

    def test_full_text_matches_input(self):
        result = ingest_text(self.SAMPLE_TEXT)
        assert result.full_text == self.SAMPLE_TEXT.strip()

    def test_default_title(self):
        result = ingest_text(self.SAMPLE_TEXT)
        assert result.title == "Untitled Document"

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="empty"):
            ingest_text("   ")

    def test_source_ref_is_raw(self):
        result = ingest_text(self.SAMPLE_TEXT)
        assert result.source_ref == "raw"


class TestPdfIngester:
    def test_missing_file_raises(self, tmp_path):
        from app.services.ingestion.pdf_ingester import ingest_pdf
        with pytest.raises(FileNotFoundError):
            ingest_pdf(tmp_path / "nonexistent.pdf")

    def test_valid_pdf(self, tmp_path):
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
        assert len(result.full_text) > 0
