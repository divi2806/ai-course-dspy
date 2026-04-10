"""Semantic text chunker with sentence-aware splitting and overlap."""

import re


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using regex (no heavy NLP dependency)."""
    # Split on sentence-ending punctuation followed by whitespace/newline
    sentence_endings = re.compile(r"(?<=[.!?])\s+")
    sentences = sentence_endings.split(text.strip())
    return [s.strip() for s in sentences if s.strip()]


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[str]:
    """
    Split *text* into overlapping chunks of approximately *chunk_size* words.

    Strategy:
    1. Split into sentences to avoid cutting mid-sentence.
    2. Accumulate sentences until the chunk word-budget is exhausted.
    3. Slide the window back by *overlap* words for continuity.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[str] = []
    current_words: list[str] = []
    current_char_count = 0

    for sentence in sentences:
        sentence_words = sentence.split()
        sentence_len = len(sentence_words)

        # If a single sentence exceeds chunk_size, hard-split it
        if sentence_len > chunk_size:
            # Flush current buffer first
            if current_words:
                chunks.append(" ".join(current_words))
                current_words = current_words[-overlap:]
                current_char_count = len(" ".join(current_words))

            # Hard-split the long sentence
            for i in range(0, sentence_len, chunk_size - overlap):
                piece = sentence_words[i : i + chunk_size]
                chunks.append(" ".join(piece))
            continue

        # Would adding this sentence exceed budget?
        if current_char_count + sentence_len > chunk_size and current_words:
            chunks.append(" ".join(current_words))
            # Carry over trailing words for overlap
            current_words = current_words[-overlap:] if overlap else []
            current_char_count = len(current_words)

        current_words.extend(sentence_words)
        current_char_count += sentence_len

    # Flush remaining buffer
    if current_words:
        chunks.append(" ".join(current_words))

    return [c for c in chunks if c.strip()]
