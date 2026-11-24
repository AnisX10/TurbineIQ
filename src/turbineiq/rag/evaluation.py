"""Score evidence retrieval on a labelled question set (hit rate and MRR)."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .documents import DocumentChunk, load_document_path
from .retrieval import SearchHit


@dataclass(frozen=True)
class EvalQuestion:
    query: str
    gold: frozenset[tuple[str, str | None]]


@dataclass(frozen=True)
class QuestionResult:
    query: str
    rank: int | None  # 1-based rank of the first relevant hit, None if missed


@dataclass(frozen=True)
class EvalReport:
    top_k: int
    results: tuple[QuestionResult, ...]
    mean_latency_ms: float

    @property
    def hit_rate(self) -> float:
        return sum(r.rank is not None for r in self.results) / len(self.results)

    @property
    def mrr(self) -> float:
        return sum(1.0 / r.rank for r in self.results if r.rank) / len(self.results)

    @property
    def misses(self) -> list[str]:
        return [r.query for r in self.results if r.rank is None]


def load_eval_set(
    path: str | Path, root: str | Path
) -> tuple[list[EvalQuestion], list[DocumentChunk]]:
    """Read the question file and the corpus it names; reject gold labels that do not exist."""

    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    chunks: list[DocumentChunk] = []
    for doc in sorted(Path(root).glob(spec["corpus_glob"])):
        chunks.extend(load_document_path(doc))
    known = {(c.source, c.section) for c in chunks}
    questions: list[EvalQuestion] = []
    for item in spec["questions"]:
        gold = frozenset((source, section) for source, section in item["gold"])
        unknown = gold - known
        if unknown:
            raise ValueError(f"gold label not in corpus for {item['q']!r}: {sorted(unknown)}")
        questions.append(EvalQuestion(query=item["q"], gold=gold))
    return questions, chunks


def evaluate(
    search: Callable[[str, list[DocumentChunk], int], Sequence[SearchHit]],
    questions: list[EvalQuestion],
    chunks: list[DocumentChunk],
    *,
    top_k: int = 4,
) -> EvalReport:
    results: list[QuestionResult] = []
    elapsed = 0.0
    for question in questions:
        start = time.perf_counter()
        hits = search(question.query, chunks, top_k)
        elapsed += time.perf_counter() - start
        rank = next(
            (
                index
                for index, hit in enumerate(hits[:top_k], start=1)
                if (hit.chunk.source, hit.chunk.section) in question.gold
            ),
            None,
        )
        results.append(QuestionResult(query=question.query, rank=rank))
    return EvalReport(
        top_k=top_k,
        results=tuple(results),
        mean_latency_ms=1000 * elapsed / max(len(questions), 1),
    )
