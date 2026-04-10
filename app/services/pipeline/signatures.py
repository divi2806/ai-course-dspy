"""DSPy typed signatures for the course generation pipeline."""

from typing import Literal

import dspy


class CleanContent(dspy.Signature):
    """
    Clean raw extracted text: remove artifacts, fix whitespace, drop
    boilerplate (headers/footers/page numbers) while preserving meaning.
    """

    raw_text: str = dspy.InputField(desc="Raw text extracted from the source material")
    cleaned_text: str = dspy.OutputField(
        desc="Clean, readable text ready for analysis"
    )


class ExtractTopics(dspy.Signature):
    """
    Identify the main topics and sub-topics covered in the content.
    Return a structured list of topic names separated by semicolons.
    """

    cleaned_text: str = dspy.InputField(desc="Clean source text")
    topics: str = dspy.OutputField(
        desc="Semicolon-separated list of topics, e.g. 'Recursion; Dynamic Programming; Graph Traversal'"
    )


class BreakdownConcepts(dspy.Signature):
    """
    For each topic, identify the core concepts a learner must understand.
    Return a JSON array of objects with 'topic' and 'concepts' (list of strings).
    """

    topics: str = dspy.InputField(desc="Semicolon-separated list of topics")
    cleaned_text: str = dspy.InputField(desc="Source text to ground the concepts in")
    concepts_json: str = dspy.OutputField(
        desc='JSON array: [{"topic": "...", "concepts": ["...", "..."]}]'
    )


class ClassifyDifficulty(dspy.Signature):
    """
    Given a list of concepts and the desired difficulty level, filter and
    annotate concepts appropriate for that level.

    - easy:   definitions, intuition, first examples
    - medium: applications, common patterns, edge cases
    - hard:   system design, optimisation, deep internals
    """

    concepts_json: str = dspy.InputField(desc="JSON array of topic-concept objects")
    difficulty: Literal["easy", "medium", "hard"] = dspy.InputField(
        desc="Target difficulty level"
    )
    filtered_concepts_json: str = dspy.OutputField(
        desc="JSON array filtered and annotated for the requested difficulty"
    )


class BuildCourse(dspy.Signature):
    """
    Build a structured course from filtered concepts for the given difficulty.

    Return a JSON object with:
    {
      "title": "<course title>",
      "summary": "<2-3 sentence overview>",
      "modules": [
        {
          "title": "...",
          "explanation": "...",
          "examples": ["..."],
          "code_snippets": ["..."],
          "key_takeaways": ["..."]
        }
      ]
    }

    Tailor explanation depth, vocabulary, and example complexity strictly to
    the requested difficulty.
    """

    filtered_concepts_json: str = dspy.InputField(
        desc="Filtered, difficulty-annotated concept list"
    )
    difficulty: Literal["easy", "medium", "hard"] = dspy.InputField(
        desc="Target difficulty level"
    )
    source_text: str = dspy.InputField(
        desc="Original source text to ground examples and explanations"
    )
    course_json: str = dspy.OutputField(
        desc="Full course as a JSON object (title, summary, modules[])"
    )
