"""Retrieval benchmark: question format, relevance judgements, metrics and reports.

Questions carry the evidence they should be answered from, written as short phrases rather
than chunk ids, so the labels survive a change of chunk size or retriever. A retrieved
chunk is *relevant* to a question when it comes from a gold source, from a gold page (when
pages are given) and contains at least one of the gold evidence phrases (when given).

Metrics are computed on the ranked chunks only. They say how well retrieval finds the
evidence; they do not measure whether a language model then answers correctly.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .documents import DocumentChunk
from .hybrid import Retriever

CATEGORIES = ("factual_document", "numeric_document", "conceptual", "unanswerable")
KS = (1, 3, 5, 10)


@dataclass(frozen=True)
class GoldPassage:
    source: str
    pages: tuple[int, ...] = ()
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class BenchmarkQuestion:
    id: str
    category: str
    question: str
    answerable: bool
    gold: tuple[GoldPassage, ...] = ()
    reference_answer: str = ""


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def load_benchmark(path: str | Path) -> list[BenchmarkQuestion]:
    """Read a JSON-lines benchmark and validate it."""

    questions: list[BenchmarkQuestion] = []
    seen: set[str] = set()
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            raw = json.loads(line)
            gold = tuple(
                GoldPassage(
                    source=str(g["source"]),
                    pages=tuple(int(p) for p in g.get("pages", ())),
                    evidence=tuple(str(e) for e in g.get("evidence", ())),
                )
                for g in raw.get("gold", ())
            )
            question = BenchmarkQuestion(
                id=str(raw["id"]),
                category=str(raw["category"]),
                question=str(raw["question"]),
                answerable=bool(raw["answerable"]),
                gold=gold,
                reference_answer=str(raw.get("reference_answer", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"benchmark line {number}: {exc!r}") from exc
        if question.category not in CATEGORIES:
            raise ValueError(f"line {number}: unknown category {question.category!r}")
        if question.id in seen:
            raise ValueError(f"line {number}: duplicate id {question.id!r}")
        if question.answerable and not question.gold:
            raise ValueError(f"line {number}: answerable question {question.id} has no gold")
        if not question.answerable and question.gold:
            raise ValueError(f"line {number}: unanswerable question {question.id} has gold")
        if question.answerable and question.category == "unanswerable":
            raise ValueError(f"line {number}: category and answerable disagree")
        seen.add(question.id)
        questions.append(question)
    if not questions:
        raise ValueError("benchmark has no questions")
    return questions


def _matches(chunk: DocumentChunk, gold: GoldPassage) -> bool:
    if chunk.source.casefold() != gold.source.casefold():
        return False
    if gold.pages and chunk.page_number not in gold.pages:
        return False
    if gold.evidence:
        text = _normalise(chunk.text)
        return any(_normalise(phrase) in text for phrase in gold.evidence)
    return True


def is_relevant(chunk: DocumentChunk, question: BenchmarkQuestion) -> bool:
    return any(_matches(chunk, gold) for gold in question.gold)


def check_gold_in_corpus(
    questions: list[BenchmarkQuestion], chunks: list[DocumentChunk]
) -> list[str]:
    """Return problems: gold that no chunk satisfies (a label or a chunking problem)."""

    problems = []
    for q in questions:
        for gold in q.gold:
            if not any(_matches(chunk, gold) for chunk in chunks):
                problems.append(f"{q.id}: no chunk satisfies gold {gold.source} {gold.pages}")
    return problems


@dataclass
class QuestionResult:
    id: str
    category: str
    answerable: bool
    first_relevant_rank: int | None
    precision_at_3: float
    context_recall_at_3: float
    top_score: float
    cited: list[str] = field(default_factory=list)


def _context_recall(question: BenchmarkQuestion, hits: list[Any], k: int) -> float:
    phrases = [(_normalise(p)) for g in question.gold for p in g.evidence]
    if not phrases:
        return 1.0 if any(is_relevant(h.chunk, question) for h in hits[:k]) else 0.0
    text = " ".join(_normalise(h.chunk.text) for h in hits[:k])
    return sum(p in text for p in phrases) / len(phrases)


def evaluate(
    retriever: Retriever, questions: list[BenchmarkQuestion], *, top_k: int = 10
) -> list[QuestionResult]:
    results = []
    for q in questions:
        hits = retriever.search(q.question, top_k)
        first = None
        if q.answerable:
            for rank, hit in enumerate(hits, start=1):
                if is_relevant(hit.chunk, q):
                    first = rank
                    break
        top3 = hits[:3]
        results.append(
            QuestionResult(
                id=q.id,
                category=q.category,
                answerable=q.answerable,
                first_relevant_rank=first,
                precision_at_3=(
                    sum(is_relevant(h.chunk, q) for h in top3) / 3 if q.answerable else 0.0
                ),
                context_recall_at_3=_context_recall(q, hits, 3) if q.answerable else 0.0,
                top_score=hits[0].score if hits else 0.0,
                cited=[h.citation for h in top3],
            )
        )
    return results


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def _bootstrap_ci(values: list[float], *, seed: int, resamples: int = 2000) -> tuple[float, float]:
    if len(values) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    means = sorted(_mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples))
    return (means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1])


def _auc(positive: list[float], negative: list[float]) -> float | None:
    """P(score of an answerable question > score of an unanswerable one); ties count half."""

    if not positive or not negative:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in positive for n in negative)
    return wins / (len(positive) * len(negative))


def summarize(results: list[QuestionResult], *, seed: int = 0) -> dict[str, Any]:
    answerable = [r for r in results if r.answerable]

    def block(rows: list[QuestionResult]) -> dict[str, Any]:
        out: dict[str, Any] = {"questions": len(rows)}
        for k in KS:
            out[f"hit_at_{k}"] = _mean(
                [
                    float(r.first_relevant_rank is not None and r.first_relevant_rank <= k)
                    for r in rows
                ]
            )
        out["mrr_at_10"] = _mean(
            [1.0 / r.first_relevant_rank if r.first_relevant_rank else 0.0 for r in rows]
        )
        out["precision_at_3"] = _mean([r.precision_at_3 for r in rows])
        out["context_recall_at_3"] = _mean([r.context_recall_at_3 for r in rows])
        return out

    overall = block(answerable)
    for metric, getter in (
        (
            "hit_at_3",
            lambda r: float(r.first_relevant_rank is not None and r.first_relevant_rank <= 3),
        ),
        (
            "hit_at_5",
            lambda r: float(r.first_relevant_rank is not None and r.first_relevant_rank <= 5),
        ),
        ("mrr_at_10", lambda r: 1.0 / r.first_relevant_rank if r.first_relevant_rank else 0.0),
    ):
        lo, hi = _bootstrap_ci([getter(r) for r in answerable], seed=seed)
        overall[f"{metric}_ci95"] = [lo, hi]
    by_category = {
        c: block([r for r in answerable if r.category == c])
        for c in CATEGORIES
        if any(r.category == c for r in answerable)
    }
    unanswerable = [r for r in results if not r.answerable]
    return {
        "answerable": overall,
        "by_category": by_category,
        "unanswerable_questions": len(unanswerable),
        "refusal_auc": _auc([r.top_score for r in answerable], [r.top_score for r in unanswerable]),
        "note": (
            "refusal_auc is the probability that an answerable question's top retrieval score "
            "exceeds an unanswerable one's (0.5 = no signal). Scores are only comparable "
            "within one configuration."
        ),
    }


def render_markdown(title: str, reports: dict[str, dict[str, Any]], meta: dict[str, Any]) -> str:
    def f(x: float) -> str:
        return "n/a" if x != x else f"{x:.3f}"

    lines = [f"# {title}", ""]
    for key, value in meta.items():
        lines.append(f"- **{key}:** {value}")
    lines += [
        "",
        "Retrieval metrics only: they measure whether the evidence is found, not whether a "
        "language model answers correctly. 95% intervals are seeded bootstrap over questions.",
        "",
        "| Configuration | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR@10 | "
        "Context recall@3 | Refusal AUC |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, rep in reports.items():
        a = rep["answerable"]
        ci3 = a["hit_at_3_ci95"]
        auc = rep["refusal_auc"]
        lines.append(
            f"| {name} | {f(a['hit_at_1'])} | {f(a['hit_at_3'])} [{f(ci3[0])}, {f(ci3[1])}] | "
            f"{f(a['hit_at_5'])} | {f(a['hit_at_10'])} | {f(a['mrr_at_10'])} | "
            f"{f(a['context_recall_at_3'])} | {'n/a' if auc is None else f'{auc:.3f}'} |"
        )
    lines += ["", "## By category (Hit@3 / MRR@10)", ""]
    categories = sorted({c for r in reports.values() for c in r["by_category"]})
    lines.append("| Configuration | " + " | ".join(categories) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in categories) + " |")
    for name, rep in reports.items():
        cells = []
        for c in categories:
            b = rep["by_category"].get(c)
            cells.append(
                "n/a" if not b else f"{f(b['hit_at_3'])} / {f(b['mrr_at_10'])} (n={b['questions']})"
            )
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
