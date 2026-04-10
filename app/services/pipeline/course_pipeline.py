import json
import logging
from functools import lru_cache
from typing import Any, Literal

import dspy

from app.core.config import get_settings
from app.models.schemas import Module
from app.services.pipeline.signatures import (
    BreakdownConcepts,
    BuildCourse,
    ClassifyDifficulty,
    CleanContent,
    ExtractTopics,
)

log = logging.getLogger(__name__)
settings = get_settings()


def _configure_lm() -> None:
    provider = settings.llm_provider
    model = settings.llm_model

    if provider == "openai":
        lm = dspy.LM(f"openai/{model}", api_key=settings.openai_api_key)
    elif provider == "anthropic":
        lm = dspy.LM(f"anthropic/{model}", api_key=settings.anthropic_api_key)
    elif provider == "ollama":
        lm = dspy.LM(f"ollama_chat/{model}", api_base=settings.ollama_base_url)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    dspy.configure(lm=lm)
    log.info("DSPy configured with %s/%s", provider, model)


def _safe_parse_json(text: str, fallback: Any = None) -> Any:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("JSON parse failed. Raw: %.200s", text)
        return fallback


class CoursePipeline(dspy.Module):
    """
    Five-stage pipeline: clean text, extract topics, break down concepts,
    filter by difficulty, then build the final course structure.
    """

    def __init__(self) -> None:
        super().__init__()
        self.clean = dspy.ChainOfThought(CleanContent)
        self.extract = dspy.ChainOfThought(ExtractTopics)
        self.breakdown = dspy.ChainOfThought(BreakdownConcepts)
        self.classify = dspy.ChainOfThought(ClassifyDifficulty)
        self.build = dspy.ChainOfThought(BuildCourse)

    def forward(self, text: str, difficulty: Literal["easy", "medium", "hard"]) -> dict:
        clean_text = self.clean(raw_text=text).cleaned_text
        topics = self.extract(cleaned_text=clean_text).topics
        concepts_json = self.breakdown(topics=topics, cleaned_text=clean_text).concepts_json
        filtered_json = self.classify(concepts_json=concepts_json, difficulty=difficulty).filtered_concepts_json
        course_json = self.build(
            filtered_concepts_json=filtered_json,
            difficulty=difficulty,
            source_text=clean_text[:6000],
        ).course_json
        return _safe_parse_json(course_json, fallback={})


@lru_cache(maxsize=1)
def get_pipeline() -> CoursePipeline:
    _configure_lm()
    return CoursePipeline()


def parse_modules(modules_data: list[dict]) -> list[Module]:
    result: list[Module] = []
    for item in modules_data:
        try:
            result.append(
                Module(
                    title=item.get("title", "Untitled Module"),
                    explanation=item.get("explanation", ""),
                    examples=item.get("examples", []),
                    code_snippets=item.get("code_snippets", []),
                    key_takeaways=item.get("key_takeaways", []),
                )
            )
        except Exception as exc:
            log.warning("Skipping malformed module: %s", exc)
    return result
