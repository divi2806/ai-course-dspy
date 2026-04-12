import json
from unittest.mock import MagicMock, patch

import pytest


SAMPLE_COURSE_JSON = json.dumps({
    "title": "Introduction to Recursion",
    "summary": "A beginner-friendly introduction to recursive thinking.",
    "modules": [
        {
            "title": "What is Recursion?",
            "explanation": "Recursion is when a function calls itself.",
            "examples": ["factorial(n) = n * factorial(n-1)"],
            "code_snippets": ["def factorial(n):\n    if n <= 1: return 1\n    return n * factorial(n-1)"],
            "key_takeaways": ["Every recursive function needs a base case."],
        }
    ],
})


class TestRLMPipeline:

    def test_run_rlm_produces_course(self):
        mock_result = MagicMock()
        mock_result.course_json = SAMPLE_COURSE_JSON

        mock_rlm = MagicMock(return_value=mock_result)

        with patch("app.services.pipeline.rlm_pipeline.get_pipeline", return_value=mock_rlm):
            from app.services.pipeline.rlm_pipeline import run_rlm
            result = run_rlm(document_text="Some text about recursion.", difficulty="easy")

        assert result["title"] == "Introduction to Recursion"
        assert len(result["modules"]) == 1
        assert result["modules"][0]["title"] == "What is Recursion?"

    def test_run_rlm_handles_fenced_json(self):
        fenced = f"```json\n{SAMPLE_COURSE_JSON}\n```"
        mock_result = MagicMock()
        mock_result.course_json = fenced

        mock_rlm = MagicMock(return_value=mock_result)

        with patch("app.services.pipeline.rlm_pipeline.get_pipeline", return_value=mock_rlm):
            from app.services.pipeline.rlm_pipeline import run_rlm
            result = run_rlm(document_text="Some text.", difficulty="medium")

        assert result["title"] == "Introduction to Recursion"

    def test_run_rlm_returns_empty_dict_on_invalid_json(self):
        mock_result = MagicMock()
        mock_result.course_json = "this is not json {{{"

        mock_rlm = MagicMock(return_value=mock_result)

        with patch("app.services.pipeline.rlm_pipeline.get_pipeline", return_value=mock_rlm):
            from app.services.pipeline.rlm_pipeline import run_rlm
            result = run_rlm(document_text="Some text.", difficulty="hard")

        assert result == {}

    def test_safe_parse_json_strips_fences(self):
        from app.services.pipeline.rlm_pipeline import _safe_parse_json
        fenced = '```json\n{"key": "value"}\n```'
        assert _safe_parse_json(fenced) == {"key": "value"}

    def test_safe_parse_json_fallback_on_invalid(self):
        from app.services.pipeline.rlm_pipeline import _safe_parse_json
        assert _safe_parse_json("not json", fallback=[]) == []

    def test_safe_parse_json_ast_literal_eval_fallback(self):
        """When LLM returns a Python dict literal (single quotes), ast.literal_eval recovers it."""
        from app.services.pipeline.rlm_pipeline import _safe_parse_json
        python_literal = "{'key': 'value', 'num': 42}"
        result = _safe_parse_json(python_literal)
        assert result == {"key": "value", "num": 42}
