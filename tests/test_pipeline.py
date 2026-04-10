"""Unit tests for the DSPy pipeline (mocked LLM)."""

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


class TestCoursePipeline:
    """Tests the pipeline with a mocked LLM so no API key is needed."""

    def _make_mock_prediction(self, **kwargs):
        pred = MagicMock()
        for k, v in kwargs.items():
            setattr(pred, k, v)
        return pred

    def test_pipeline_produces_course(self):
        from app.services.pipeline.course_pipeline import CoursePipeline

        pipeline = CoursePipeline()

        # Mock each ChainOfThought step
        pipeline.clean = MagicMock(
            return_value=self._make_mock_prediction(cleaned_text="Clean text about recursion.")
        )
        pipeline.extract = MagicMock(
            return_value=self._make_mock_prediction(topics="Recursion; Base Case; Stack")
        )
        pipeline.breakdown = MagicMock(
            return_value=self._make_mock_prediction(
                concepts_json=json.dumps([{"topic": "Recursion", "concepts": ["base case", "stack frame"]}])
            )
        )
        pipeline.classify = MagicMock(
            return_value=self._make_mock_prediction(
                filtered_concepts_json=json.dumps([{"topic": "Recursion", "concepts": ["base case"]}])
            )
        )
        pipeline.build = MagicMock(
            return_value=self._make_mock_prediction(course_json=SAMPLE_COURSE_JSON)
        )

        result = pipeline(text="Some text about recursion.", difficulty="easy")

        assert result["title"] == "Introduction to Recursion"
        assert len(result["modules"]) == 1
        assert result["modules"][0]["title"] == "What is Recursion?"

    def test_parse_modules_valid(self):
        from app.services.pipeline.course_pipeline import parse_modules

        data = json.loads(SAMPLE_COURSE_JSON)["modules"]
        modules = parse_modules(data)
        assert len(modules) == 1
        assert modules[0].title == "What is Recursion?"
        assert modules[0].examples == ["factorial(n) = n * factorial(n-1)"]

    def test_parse_modules_skips_malformed(self):
        from app.services.pipeline.course_pipeline import parse_modules

        data = [
            {"title": "Good Module", "explanation": "text", "examples": [], "code_snippets": [], "key_takeaways": []},
            {"bad_field": 123},  # missing required 'title'
        ]
        modules = parse_modules(data)
        # Should parse at least the first valid one (second may default title)
        assert len(modules) >= 1

    def test_safe_parse_json_strips_fences(self):
        from app.services.pipeline.course_pipeline import _safe_parse_json

        fenced = "```json\n{\"key\": \"value\"}\n```"
        result = _safe_parse_json(fenced)
        assert result == {"key": "value"}

    def test_safe_parse_json_returns_fallback_on_invalid(self):
        from app.services.pipeline.course_pipeline import _safe_parse_json

        result = _safe_parse_json("not json at all {{}", fallback=[])
        assert result == []
