"""Small local lexical retriever with deterministic ranking and citations."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Protocol

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


# Turbine abbreviations and their spelled-out forms. A query that spells a term out also
# searches for the abbreviation, so "compressor discharge temperature" finds "CDT". The
# reverse (abbreviation -> words) lowered MRR on the eval set: the write-ups use the
# abbreviations, and the spelled-out words are common enough to pull in unrelated chunks.
GLOSSARY: dict[str, str] = {
    "igv": "inlet guide vane",
    "cdt": "compressor discharge temperature",
    "cdp": "compressor discharge pressure",
    "egt": "exhaust gas temperature",
    "tit": "turbine inlet temperature",
    "ukf": "unscented kalman filter",
    "lhv": "lower heating value",
    "hrsg": "heat recovery steam generator",
    "fsr": "fuel stroke reference",
    "cusum": "cumulative sum",
    "mewma": "multivariate exponentially weighted moving average",
    "scada": "supervisory control data acquisition",
    "plc": "programmable logic controller",
    "dcs": "distributed control system",
    "llm": "language model",
    "tc": "thermocouple",
}
EXPANSION_WEIGHT = 1.0
HEADING_WEIGHT = 1.0  # a heading match counts as this many body occurrences
K1 = 1.2
B = 0.75


def _stem(token: str) -> str:
    """Strip common English inflections so fouled/fouling/foul and run/runs meet."""

    if len(token) <= 3 or not token.isalpha():
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("sses"):
        return token[:-2]
    if token.endswith("ing") and len(token) > 5:
        token = token[:-3]
    elif token.endswith("ed") and len(token) > 4:
        token = token[:-2]
    elif token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    else:
        return token
    # washing -> wash, but running -> runn -> run, stopped -> stopp -> stop
    if len(token) > 3 and token[-1] == token[-2] and token[-1] not in "lsz":
        token = token[:-1]
    return token


def _raw_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for word in re.findall(r"\w+", text.casefold(), flags=re.UNICODE):
        parts = [part for part in word.split("_") if part]
        if len(parts) > 1:
            tokens.append(word)  # keep score_tracking as a whole word too
        tokens.extend(parts)
    return [token for token in tokens if len(token) > 1 and token not in STOP_WORDS]


def _tokens(text: str) -> list[str]:
    return [_stem(token) for token in _raw_tokens(text)]


_GLOSSARY_STEMS = [
    (_stem(abbreviation), tuple(_tokens(expansion))) for abbreviation, expansion in GLOSSARY.items()
]


def _query_weights(query: str) -> dict[str, float]:
    tokens = _tokens(query)
    weights = {token: 1.0 for token in tokens}
    present = set(tokens)
    for abbreviation, expansion in _GLOSSARY_STEMS:
        if abbreviation not in present and expansion and set(expansion) <= present:
            weights.setdefault(abbreviation, EXPANSION_WEIGHT)
    return weights


def lexical_search(
    query: str,
    chunks: list[DocumentChunk],
    *,
    top_k: int = 4,
) -> list[SearchHit]:
    """BM25 over chunk text plus its section heading, with stemming and glossary expansion."""

    if not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be an integer of at least 1")
    query_weights = _query_weights(query)
    if not query_weights or not chunks:
        return []

    body_tokens = [_tokens(chunk.text) for chunk in chunks]
    heading_tokens = [set(_tokens(chunk.section or "")) for chunk in chunks]
    document_frequency: dict[str, int] = {}
    for body, heading in zip(body_tokens, heading_tokens, strict=True):
        for token in set(body) | heading:
            document_frequency[token] = document_frequency.get(token, 0) + 1
    average_length = sum(map(len, body_tokens)) / max(len(body_tokens), 1)
    hits: list[SearchHit] = []

    for chunk, body, heading in zip(chunks, body_tokens, heading_tokens, strict=True):
        frequency: dict[str, int] = {}
        for token in body:
            frequency[token] = frequency.get(token, 0) + 1
        length_norm = K1 * (1 - B + B * len(body) / max(average_length, 1))
        score = 0.0
        for term, weight in query_weights.items():
            tf = frequency.get(term, 0) + (HEADING_WEIGHT if term in heading else 0.0)
            if not tf:
                continue
            df = document_frequency.get(term, 0)
            inverse_document_frequency = math.log1p((len(chunks) - df + 0.5) / (df + 0.5))
            score += weight * inverse_document_frequency * tf * (K1 + 1) / (tf + length_norm)
        if score > 0:
            hits.append(SearchHit(chunk=chunk, score=score))

    hits.sort(key=lambda hit: (-hit.score, hit.chunk.source, hit.chunk.chunk_index))
    return hits[:top_k]


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, hits: list[SearchHit]) -> list[SearchHit]:
        """Return the same hits re-scored and sorted best first."""
        ...


# On the eval set 20 candidates scored the same as 30 at half the reranking time; 10 lost
# two questions from the top 4. Reranking costs roughly 40-80 ms per candidate on CPU.
RERANK_CANDIDATES = 20


def search_documents(
    query: str,
    chunks: list[DocumentChunk],
    *,
    top_k: int = 4,
    reranker: Reranker | None = None,
    candidates: int = RERANK_CANDIDATES,
) -> list[SearchHit]:
    """Lexical search, optionally re-scoring the first `candidates` hits with a reranker.

    Without a reranker this is purely local and deterministic. A reranker only reorders
    passages the lexical stage found, so it never invents evidence.
    """

    if reranker is None:
        return lexical_search(query, chunks, top_k=top_k)
    pool = lexical_search(query, chunks, top_k=max(top_k, candidates))
    if not pool:
        return []
    return reranker.rerank(query, pool)[:top_k]


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
