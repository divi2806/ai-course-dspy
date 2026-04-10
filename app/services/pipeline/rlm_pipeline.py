import ast
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import dspy
from dspy.primitives.python_interpreter import PythonInterpreter

from app.core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# Directory where runner.js and node_modules/pyodide live
_PRIMITIVES_DIR = Path(dspy.__file__).parent / "primitives"


class CourseSignature(dspy.Signature):
    """
    You are an expert course designer. You have access to the full document
    as the variable `document_text` and the difficulty level as `difficulty`.

    PHASE 1 — EXPLORATION (use the REPL for this):
      Step 1. Print the first 3000 characters to understand the document structure and subject.
      Step 2. Identify 5-10 major topics or sections in the document.
      Step 3. For each topic, extract the key content: definitions, explanations, examples,
              statistics, case studies, and any code or formulas present.
      Step 4. Store your findings in a Python dict called `modules_data` keyed by topic title.

    Difficulty calibration:
      - easy:   clear definitions, intuition, relatable analogies, no prior knowledge assumed
      - medium: real applications, common patterns, moderate depth, some domain familiarity assumed
      - hard:   edge cases, internals, trade-offs, advanced analysis, expert-level depth

    PHASE 2 — CONSTRUCTION (build the course in the REPL before submitting):
      For each topic in `modules_data`, construct a module dict with these EXACT keys:
        - "title": concise module title
        - "explanation": 3-5 sentence detailed paragraph covering the concept thoroughly.
                         DO NOT leave this empty. Draw directly from the document text.
        - "examples": list of 2-3 concrete, specific examples taken from or inspired by the document
        - "code_snippets": list of code examples if the document contains code, else []
        - "key_takeaways": list of 3-5 precise bullet points summarising the module

      Build the final course dict in the REPL:
        course = {
            "title": "<descriptive course title>",
            "summary": "<2-3 sentence overview of what the course covers>",
            "modules": [<list of module dicts>]
        }
      Then print(json.dumps(course)) to verify it is valid JSON.

    PHASE 3 — SUBMIT:
      Call SUBMIT with the course JSON string. Use double quotes throughout. No markdown fences.
    """

    document_text: str = dspy.InputField(
        desc="Full document text to build the course from"
    )
    difficulty: str = dspy.InputField(
        desc="Target difficulty level: easy, medium, or hard"
    )
    course_json: str = dspy.OutputField(
        desc=(
            'Valid JSON string with EXACTLY these keys: '
            '{"title": "...", "summary": "...", "modules": ['
            '{"title": "...", "explanation": "detailed 3-5 sentence paragraph, never empty", '
            '"examples": ["specific example 1", "specific example 2"], '
            '"code_snippets": ["..."], "key_takeaways": ["point 1", "point 2", "point 3"]}]}. '
            'Double quotes only. No markdown fences. No Python dict literals.'
        )
    )


def _configure_lm() -> None:
    provider = settings.llm_provider
    model = settings.llm_model

    if provider == "openai":
        lm = dspy.LM(f"openai/{model}", api_key=settings.openai_api_key)
    elif provider == "anthropic":
        lm = dspy.LM(f"anthropic/{model}", api_key=settings.anthropic_api_key)
    elif provider == "gemini":
        lm = dspy.LM(f"gemini/{model}", api_key=settings.gemini_api_key)
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
        pass
    # LLMs sometimes return Python dict literals (single quotes) — try ast as fallback
    try:
        result = ast.literal_eval(text)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass
    log.warning("JSON parse failed. Raw: %.200s", text)
    return fallback


def _build_interpreter() -> PythonInterpreter:
    """
    Build a PythonInterpreter with --node-modules-dir=auto so Deno 2.x
    can resolve npm:pyodide from the node_modules installed alongside runner.js.
    """
    runner_path = str(_PRIMITIVES_DIR / "runner.js")
    node_modules_path = str(_PRIMITIVES_DIR / "node_modules")

    deno_command = [
        "deno", "run",
        "--node-modules-dir=auto",
        f"--allow-read={runner_path},{node_modules_path}",
        runner_path,
    ]
    return PythonInterpreter(deno_command=deno_command)


@lru_cache(maxsize=1)
def get_pipeline() -> dspy.RLM:
    _configure_lm()
    return dspy.RLM(
        CourseSignature,
        max_iterations=30,
        max_llm_calls=60,
        max_output_chars=100_000,
        interpreter=_build_interpreter(),
    )


def run_rlm(document_text: str, difficulty: str) -> dict:
    pipeline = get_pipeline()
    result = pipeline(document_text=document_text, difficulty=difficulty)
    return _safe_parse_json(result.course_json, fallback={})
