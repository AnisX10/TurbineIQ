"""Small local lexical retriever with deterministic ranking and citations."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .documents import DocumentChunk

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "with",
}
NO_EVIDENCE = "I could not find a supporting passage in the locally indexed documents."


@dataclass(frozen=True)
class SearchHit:
    chunk: DocumentChunk
    score: float

    @property
    def citation(self) -> str:
        return self.chunk.citation


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[\w]+", text.casefold(), flags=re.UNICODE)
        if len(token) > 1 and token not in STOP_WORDS
    ]


def search_documents(
    query: str,
    chunks: list[DocumentChunk],
    *,
    top_k: int = 4,
) -> list[SearchHit]:
    """Rank chunks by local BM25-style lexical relevance; no external model."""

    if not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be an integer of at least 1")
    query_terms = set(_tokens(query))
    if not query_terms or not chunks:
        return []

    token_lists = [_tokens(chunk.text) for chunk in chunks]
    document_frequency: dict[str, int] = {}
    for tokens in token_lists:
        for token in set(tokens):
            document_frequency[token] = document_frequency.get(token, 0) + 1
    average_length = sum(map(len, token_lists)) / max(len(token_lists), 1)
    k1 = 1.2
    b = 0.75
    hits: list[SearchHit] = []

    for chunk, tokens in zip(chunks, token_lists, strict=True):
        frequency: dict[str, int] = {}
        for token in tokens:
            frequency[token] = frequency.get(token, 0) + 1
        score = 0.0
        for term in query_terms:
            tf = frequency.get(term, 0)
            if not tf:
                continue
            df = document_frequency.get(term, 0)
            inverse_document_frequency = math.log1p((len(chunks) - df + 0.5) / (df + 0.5))
            denominator = tf + k1 * (1 - b + b * len(tokens) / max(average_length, 1))
            score += inverse_document_frequency * tf * (k1 + 1) / denominator
        if score > 0:
            hits.append(SearchHit(chunk=chunk, score=score))

    hits.sort(key=lambda hit: (-hit.score, hit.chunk.source, hit.chunk.chunk_index))
    return hits[:top_k]


def build_local_answer(query: str, hits: list[SearchHit], *, excerpt_chars: int = 520) -> str:
    """Return grounded excerpts instead of inventing a synthesis without an LLM."""

    if not hits:
        return NO_EVIDENCE
    if excerpt_chars < 80:
        raise ValueError("excerpt_chars must be at least 80")
    excerpts: list[str] = []
    for hit in hits[:3]:
        excerpt = " ".join(hit.chunk.text.split())
        if len(excerpt) > excerpt_chars:
            excerpt = excerpt[:excerpt_chars].rsplit(" ", 1)[0] + "…"
        excerpts.append(f"- {excerpt} {hit.citation}")
    return (
        f"Local evidence for “{query.strip()}” (excerpts only; no cloud model used):\n\n"
        + "\n\n".join(excerpts)
    )
