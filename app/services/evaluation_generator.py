import json
import logging
from typing import Literal

import dspy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Course, Evaluation
from app.models.schemas import EvaluationResponse, MCQOption, MCQQuestion

log = logging.getLogger(__name__)


class MCQSignature(dspy.Signature):
    """
    You are an expert educator creating a high-quality MCQ quiz for a course module.

    You are given rich module content: explanation, analogies, examples, real-world
    applications, common misconceptions, key takeaways, and glossary terms.

    Use ALL of this content to write questions that test genuine understanding:
    - Draw questions from misconceptions (test if learner avoids the wrong mental model)
    - Draw questions from real-world applications (can they apply the concept?)
    - Draw questions from glossary terms (do they know the precise definition?)
    - Draw questions from examples (do they understand why the example illustrates the concept?)
    - Vary types: definition, application, comparison, cause-and-effect, misconception-busting

    For each question:
    - Write a clear, unambiguous question stem
    - Provide exactly 4 options (A, B, C, D) — one correct, three plausible distractors
    - Distractors should reflect common wrong answers or misconceptions, not random noise
    - Write a 1-2 sentence explanation of why the correct answer is right

    Return a JSON array with EXACTLY these keys per object:
    [
      {
        "question": "...",
        "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
        "correct_answer": "A",
        "explanation": "..."
      }
    ]
    No markdown fences. Valid JSON only.
    """

    module_title: str = dspy.InputField(desc="Title of the course module")
    explanation: str = dspy.InputField(desc="Detailed explanation of the module content")
    analogies: str = dspy.InputField(desc="Analogies used to explain the concept")
    examples: str = dspy.InputField(desc="Concrete examples from the module")
    real_world_applications: str = dspy.InputField(desc="Real-world applications of the concept")
    common_misconceptions: str = dspy.InputField(desc="Common misconceptions and their corrections")
    key_takeaways: str = dspy.InputField(desc="Key takeaways from the module")
    glossary: str = dspy.InputField(desc="Key terms and definitions introduced in the module")
    num_questions: int = dspy.InputField(desc="Number of MCQ questions to generate")
    questions_json: str = dspy.OutputField(
        desc='JSON array of MCQ objects with keys: question, options (A/B/C/D), correct_answer, explanation'
    )


_mcq_generator = dspy.ChainOfThought(MCQSignature)


def _questions_per_module(num_modules: int) -> int:
    """Scale questions per module so total coverage is meaningful."""
    if num_modules <= 3:
        return 4
    if num_modules <= 6:
        return 3
    return 2


def _safe_parse_questions(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    log.warning("MCQ JSON parse failed. Raw: %.300s", text)
    return []


def _build_mcq_question(raw: dict, module_title: str) -> MCQQuestion | None:
    try:
        opts = raw.get("options", {})
        return MCQQuestion(
            module_title=module_title,
            question=raw["question"],
            options=MCQOption(
                A=opts.get("A", ""),
                B=opts.get("B", ""),
                C=opts.get("C", ""),
                D=opts.get("D", ""),
            ),
            correct_answer=raw["correct_answer"].upper(),
            explanation=raw.get("explanation", ""),
        )
    except Exception as exc:
        log.warning("Skipping malformed MCQ question: %s", exc)
        return None


async def generate_evaluation(
    course_id: str,
    db: AsyncSession,
) -> EvaluationResponse:
    result = await db.execute(select(Course).where(Course.id == course_id))
    course: Course | None = result.scalar_one_or_none()
    if course is None:
        raise ValueError(f"Course not found: {course_id}")

    modules = json.loads(course.modules_json)
    if not modules:
        raise ValueError(f"Course {course_id} has no modules to evaluate on.")

    num_q = _questions_per_module(len(modules))
    all_questions: list[MCQQuestion] = []

    for module in modules:
        title = module.get("title", "Untitled Module")
        explanation = module.get("explanation", "")
        analogies = "; ".join(module.get("analogies", []))
        examples = "; ".join(module.get("examples", []))
        real_world_applications = "; ".join(module.get("real_world_applications", []))
        common_misconceptions = "; ".join(module.get("common_misconceptions", []))
        key_takeaways = "; ".join(module.get("key_takeaways", []))
        glossary_raw = module.get("glossary", [])
        glossary = "; ".join(
            f"{g['term']}: {g['definition']}"
            for g in glossary_raw
            if isinstance(g, dict) and "term" in g and "definition" in g
        )

        if not explanation and not key_takeaways:
            log.warning("Skipping module '%s' — no content to generate questions from", title)
            continue

        log.info("Generating %d MCQs for module: %s", num_q, title)
        try:
            pred = _mcq_generator(
                module_title=title,
                explanation=explanation,
                analogies=analogies,
                examples=examples,
                real_world_applications=real_world_applications,
                common_misconceptions=common_misconceptions,
                key_takeaways=key_takeaways,
                glossary=glossary,
                num_questions=num_q,
            )
            raw_questions = _safe_parse_questions(pred.questions_json)
            for raw in raw_questions[:num_q]:
                q = _build_mcq_question(raw, title)
                if q:
                    all_questions.append(q)
        except Exception as exc:
            log.warning("MCQ generation failed for module '%s': %s", title, exc)

    evaluation = Evaluation(
        course_id=course_id,
        questions_json=json.dumps([q.model_dump() for q in all_questions]),
    )
    db.add(evaluation)
    await db.flush()

    log.info(
        "Evaluation %s created for course %s (%d questions)",
        evaluation.id, course_id, len(all_questions),
    )

    return EvaluationResponse(
        evaluation_id=evaluation.id,
        course_id=course_id,
        course_title=course.title,
        total_questions=len(all_questions),
        questions=all_questions,
        created_at=evaluation.created_at,
    )


async def get_evaluation(evaluation_id: str, db: AsyncSession) -> EvaluationResponse:
    result = await db.execute(
        select(Evaluation).where(Evaluation.id == evaluation_id)
    )
    evaluation: Evaluation | None = result.scalar_one_or_none()
    if evaluation is None:
        raise ValueError(f"Evaluation not found: {evaluation_id}")

    result = await db.execute(select(Course).where(Course.id == evaluation.course_id))
    course: Course = result.scalar_one()

    raw_questions = json.loads(evaluation.questions_json)
    questions = []
    for raw in raw_questions:
        try:
            opts = raw["options"]
            questions.append(MCQQuestion(
                module_title=raw["module_title"],
                question=raw["question"],
                options=MCQOption(**opts),
                correct_answer=raw["correct_answer"],
                explanation=raw["explanation"],
            ))
        except Exception as exc:
            log.warning("Skipping malformed stored question: %s", exc)

    return EvaluationResponse(
        evaluation_id=evaluation.id,
        course_id=evaluation.course_id,
        course_title=course.title,
        total_questions=len(questions),
        questions=questions,
        created_at=evaluation.created_at,
    )
