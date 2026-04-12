import logging

import httpx

from app.models.schemas import IngestedContent

log = logging.getLogger(__name__)

_PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
_MODEL = "sonar-pro"
_TIMEOUT = 120.0


def _build_research_prompt(topic: str, details: str | None, focus_areas: list[str]) -> str:
    parts = [
        f"Write a comprehensive, well-structured research report on: **{topic}**.",
    ]

    if details:
        parts.append(f"Additional context: {details}")

    if focus_areas:
        areas = ", ".join(focus_areas)
        parts.append(f"Make sure to cover these specific areas: {areas}")

    parts += [
        "",
        "Structure the report with the following sections:",
        "1. Overview — what this topic is, why it matters, historical context if relevant",
        "2. Core Concepts — the fundamental ideas, definitions, and principles",
        "3. How It Works — mechanisms, processes, or methodology in detail",
        "4. Key Components or Types — categories, variations, or sub-topics",
        "5. Real-World Applications — concrete use cases, industries, or examples",
        "6. Benefits and Challenges — advantages, limitations, trade-offs",
        "7. Current State and Trends — latest developments, state of the field",
        "8. Key Facts and Statistics — notable data points, numbers, benchmarks",
        "",
        "Be thorough and detailed. Include specific examples, case studies, and data where available.",
        "Write for someone who wants to deeply understand this topic.",
        "Cite your sources inline where applicable.",
    ]

    return "\n".join(parts)


def _format_report(topic: str, content: str, citations: list[str]) -> str:
    """Combine the research content with a formatted sources section."""
    lines = [content.strip(), ""]

    if citations:
        lines += ["", "---", "## Sources", ""]
        for i, url in enumerate(citations, 1):
            lines.append(f"{i}. {url}")

    return "\n".join(lines)


async def ingest_topic(
    topic: str,
    api_key: str,
    details: str | None = None,
    focus_areas: list[str] | None = None,
    title: str | None = None,
) -> tuple[IngestedContent, list[str]]:
    """
    Research a topic using Perplexity's sonar-pro model and return
    the compiled report as IngestedContent alongside the citation URLs.
    """
    focus_areas = focus_areas or []
    prompt = _build_research_prompt(topic, details, focus_areas)

    payload = {
        "model": _MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert researcher and technical writer. "
                    "Produce comprehensive, accurate, well-structured research reports "
                    "with specific details, examples, and data. Never be vague."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 4000,
        "temperature": 0.2,
        "return_citations": True,
        "search_recency_filter": "month",
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    log.info("Researching topic '%s' via Perplexity sonar-pro", topic)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(_PERPLEXITY_URL, json=payload, headers=headers)

    if response.status_code != 200:
        raise RuntimeError(
            f"Perplexity API error {response.status_code}: {response.text[:300]}"
        )

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    citations: list[str] = data.get("citations", [])

    full_report = _format_report(topic, content, citations)
    doc_title = title or f"Research Report: {topic}"

    log.info(
        "Topic research complete: %d words, %d sources",
        len(full_report.split()),
        len(citations),
    )

    ingested = IngestedContent(
        source_type="text",
        source_ref=f"perplexity:sonar-pro:{topic}",
        title=doc_title,
        full_text=full_report,
    )

    return ingested, citations
