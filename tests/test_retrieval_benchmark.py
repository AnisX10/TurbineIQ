"""Retrievers, fusion and the benchmark metrics, on small hand-checkable examples."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from turbineiq.rag import (
    Bm25Retriever,
    DenseRetriever,
    DocumentChunk,
    HybridRetriever,
    LexicalBaseline,
    RerankedRetriever,
    SearchHit,
    reciprocal_rank_fusion,
    search_documents,
)
from turbineiq.rag.evaluation import (
    BenchmarkQuestion,
    GoldPassage,
    check_gold_in_corpus,
    evaluate,
    is_relevant,
    load_benchmark,
    render_markdown,
    summarize,
)

ROOT = Path(__file__).resolve().parents[1]


def chunk(source: str, index: int, text: str, page: int | None = None) -> DocumentChunk:
    return DocumentChunk(
        text=text, source=source, page_number=page, section=None, chunk_index=index
    )


CORPUS = [
    chunk("a.pdf", 0, "The compressor raises air pressure before combustion in the cycle.", 1),
    chunk("a.pdf", 1, "Turbine exhaust temperature rises when firing temperature increases.", 2),
    chunk("b.pdf", 0, "An automobile engine burns petrol in reciprocating cylinders.", 1),
    chunk("b.pdf", 1, "Heat rate expresses fuel energy per unit of electrical output.", 2),
    chunk("c.md", 0, "Variable inlet guide vanes control airflow at part load.", None),
]


class SynonymEmbedder:
    """Test double: a tiny hand-made 'semantic' space where car and automobile coincide."""

    name = "synonym-test-double"
    concepts = {
        "car": 0, "automobile": 0, "petrol": 0, "engine": 0,
        "compressor": 1, "pressure": 1, "air": 1,
        "exhaust": 2, "temperature": 2, "firing": 2,
        "heat": 3, "rate": 3, "fuel": 3, "efficiency": 3,
        "vanes": 4, "guide": 4, "airflow": 4,
    }  # fmt: skip

    def __init__(self) -> None:
        self.calls: list[tuple[int, bool]] = []

    def embed(self, texts, *, is_query: bool) -> np.ndarray:
        self.calls.append((len(texts), is_query))
        out = np.zeros((len(texts), 5), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in text.casefold().replace(".", "").split():
                if word in self.concepts:
                    out[row, self.concepts[word]] += 1.0
        return out


def test_bm25_retriever_matches_the_shipped_search_exactly() -> None:
    retriever = Bm25Retriever(CORPUS)
    for query in ("exhaust temperature firing", "heat rate fuel", "air pressure compressor", "zzz"):
        expected = search_documents(query, CORPUS, top_k=5)
        got = retriever.search(query, 5)
        assert [(h.chunk.source, h.chunk.chunk_index) for h in got] == [
            (h.chunk.source, h.chunk.chunk_index) for h in expected
        ]
        assert [h.score for h in got] == pytest.approx([h.score for h in expected])
    assert LexicalBaseline(CORPUS).search("heat rate", 2)[0].chunk.source == "b.pdf"
    with pytest.raises(ValueError):
        retriever.search("x", 0)


def test_reciprocal_rank_fusion_scores_by_rank() -> None:
    a, b, c = CORPUS[0], CORPUS[1], CORPUS[2]
    first = [SearchHit(a, 9.0), SearchHit(b, 5.0)]
    second = [SearchHit(b, 0.9), SearchHit(c, 0.5), SearchHit(a, 0.1)]
    fused = reciprocal_rank_fusion([first, second], k=60)
    scores = {(h.chunk.source, h.chunk.chunk_index): h.score for h in fused}
    assert scores[("a.pdf", 1)] == pytest.approx(1 / 62 + 1 / 61)
    assert scores[("a.pdf", 0)] == pytest.approx(1 / 61 + 1 / 63)
    assert scores[("b.pdf", 0)] == pytest.approx(1 / 62)
    assert [h.chunk.chunk_index for h in fused][:2] == [1, 0]  # b (rank 2,1) beats a (1,3)
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([first], k=0)


def test_dense_retriever_finds_a_synonym_that_lexical_search_misses(tmp_path: Path) -> None:
    embedder = SynonymEmbedder()
    dense = DenseRetriever(CORPUS, embedder, cache_dir=tmp_path)
    assert Bm25Retriever(CORPUS).search("car", 3) == []  # no shared word
    top = dense.search("car", 1)[0]
    assert (top.chunk.source, top.chunk.chunk_index) == ("b.pdf", 0)
    assert embedder.calls[-1] == (1, True)  # the query was embedded as a query
    assert all(is_query is False for _, is_query in embedder.calls[:-1])


def test_dense_retriever_reuses_the_embedding_cache(tmp_path: Path) -> None:
    first = SynonymEmbedder()
    DenseRetriever(CORPUS, first, cache_dir=tmp_path)
    second = SynonymEmbedder()
    DenseRetriever(CORPUS, second, cache_dir=tmp_path)
    assert first.calls and not second.calls
    assert len(list(tmp_path.glob("embeddings-*.npy"))) == 1


def test_hybrid_combines_exact_terms_and_meaning() -> None:
    bm25 = Bm25Retriever(CORPUS)
    dense = DenseRetriever(CORPUS, SynonymEmbedder())
    hybrid = HybridRetriever([bm25, dense], candidate_k=5)
    hits = hybrid.search("car guide vanes", 5)
    sources = {(h.chunk.source, h.chunk.chunk_index) for h in hits}
    assert ("b.pdf", 0) in sources  # found by meaning only
    assert ("c.md", 0) in sources  # found by exact words
    assert hybrid.search("   ", 3) == []


def test_reranker_reorders_candidates_and_passes_the_passages() -> None:
    seen: dict[str, object] = {}

    class Reverse:
        name = "fake-reranker"

        def score(self, query, passages):
            seen["query"], seen["n"] = query, len(passages)
            return [float(i) for i in range(len(passages))]  # last candidate wins

    base = Bm25Retriever(CORPUS)
    candidates = base.search("temperature fuel heat air", 5)
    reranked = RerankedRetriever(base, Reverse(), candidate_k=5).search(
        "temperature fuel heat air", 2
    )
    assert reranked[0].chunk == candidates[-1].chunk
    assert seen["n"] == len(candidates)


def _question(**kw) -> BenchmarkQuestion:
    defaults = dict(id="q", category="factual_document", question="?", answerable=True)
    return BenchmarkQuestion(**{**defaults, **kw})


def test_relevance_uses_source_page_and_evidence_phrase() -> None:
    q = _question(gold=(GoldPassage("a.pdf", pages=(2,), evidence=("firing temperature",)),))
    assert is_relevant(CORPUS[1], q)
    assert not is_relevant(CORPUS[0], q)  # wrong page and no phrase
    assert not is_relevant(chunk("a.pdf", 5, "firing temperature again", page=3), q)  # wrong page
    assert not is_relevant(chunk("z.pdf", 0, "firing temperature", page=2), q)  # wrong source
    spaced = chunk("a.pdf", 7, "Firing\n  Temperature  matters", page=2)
    assert is_relevant(spaced, q)  # whitespace and case are normalised


class FixedRetriever:
    def __init__(self, table):
        self.table = table

    def search(self, query, top_k=4):
        return [SearchHit(c, s) for c, s in self.table[query]][:top_k]


def test_metrics_match_hand_computation() -> None:
    gold_a = (GoldPassage("a.pdf", evidence=("compressor raises",)),)
    gold_b = (GoldPassage("b.pdf", evidence=("heat rate", "fuel energy")),)
    questions = [
        _question(id="q1", question="one", gold=gold_a),
        _question(id="q2", question="two", gold=gold_b),
        _question(id="q3", question="three", category="unanswerable", answerable=False),
    ]
    table = {
        "one": [(CORPUS[0], 3.0), (CORPUS[2], 2.0)],  # relevant at rank 1
        "two": [(CORPUS[2], 4.0), (CORPUS[4], 3.0), (CORPUS[3], 2.0)],  # relevant at rank 3
        "three": [(CORPUS[2], 1.0)],
    }
    results = evaluate(FixedRetriever(table), questions)
    assert [r.first_relevant_rank for r in results] == [1, 3, None]
    assert results[0].precision_at_3 == pytest.approx(1 / 3)
    assert results[1].context_recall_at_3 == pytest.approx(1.0)  # both phrases are in chunk b1
    assert results[0].context_recall_at_3 == pytest.approx(1.0)

    summary = summarize(results, seed=1)
    a = summary["answerable"]
    assert a["questions"] == 2
    assert a["hit_at_1"] == pytest.approx(0.5)
    assert a["hit_at_3"] == pytest.approx(1.0)
    assert a["mrr_at_10"] == pytest.approx((1 + 1 / 3) / 2)
    # top scores: answerable 3.0 and 4.0, unanswerable 1.0 -> AUC 1.0
    assert summary["refusal_auc"] == pytest.approx(1.0)
    assert summary["unanswerable_questions"] == 1
    assert summarize(results, seed=1) == summary  # seeded bootstrap is reproducible
    lo, hi = a["hit_at_3_ci95"]
    assert lo <= 1.0 <= hi


def test_gold_check_reports_labels_no_chunk_can_satisfy() -> None:
    ok = _question(id="ok", gold=(GoldPassage("a.pdf", evidence=("compressor",)),))
    bad = _question(id="bad", gold=(GoldPassage("a.pdf", evidence=("not in the corpus",)),))
    problems = check_gold_in_corpus([ok, bad], CORPUS)
    assert len(problems) == 1 and problems[0].startswith("bad")


def test_markdown_report_lists_every_configuration() -> None:
    q = [_question(gold=(GoldPassage("a.pdf", evidence=("compressor",)),))]
    rep = summarize(evaluate(Bm25Retriever(CORPUS), q))
    text = render_markdown("T", {"bm25": rep, "other": rep}, {"questions": 1})
    assert "| bm25 |" in text and "| other |" in text and "Retrieval metrics only" in text


def test_benchmark_loader_rejects_inconsistent_questions(tmp_path: Path) -> None:
    def write(*rows) -> Path:
        path = tmp_path / "q.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        return path

    good = {"id": "a", "category": "conceptual", "question": "q", "answerable": True,
            "gold": [{"source": "a.pdf", "evidence": ["x"]}]}  # fmt: skip
    assert load_benchmark(write(good))[0].gold[0].evidence == ("x",)
    for bad in (
        {**good, "category": "nonsense"},
        {**good, "gold": []},
        {**good, "answerable": False},
        {
            "id": "u",
            "category": "unanswerable",
            "question": "q",
            "answerable": True,
            "gold": [{"source": "a.pdf"}],
        },  # fmt: skip
    ):
        with pytest.raises(ValueError):
            load_benchmark(write(bad))
    with pytest.raises(ValueError):
        load_benchmark(write(good, good))  # duplicate id


def test_runner_reports_unavailable_models_instead_of_inventing_results(tmp_path: Path) -> None:
    corpus = tmp_path / "files"
    corpus.mkdir()
    (corpus / "notes.md").write_text(
        "# Notes\n\nThe compressor raises air pressure. Heat rate is fuel energy per kWh.\n",
        encoding="utf-8",
    )
    questions = tmp_path / "q.jsonl"
    questions.write_text(
        json.dumps({"id": "q1", "category": "conceptual", "question": "compressor pressure",
                    "answerable": True,
                    "gold": [{"source": "notes.md", "evidence": ["compressor raises"]}]})
        + "\n",
        encoding="utf-8",
    )  # fmt: skip
    out = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_retrieval_benchmark.py"),
         "--corpus-dir", str(corpus), "--benchmark", str(questions), "--out-dir", str(out),
         "--label", "t", "--configs", "lexical_baseline,bm25,dense",
         "--embedding-model", "no-such/model", "--cache-dir", str(tmp_path / "cache")],
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    payload = json.loads((out / "t.json").read_text(encoding="utf-8"))
    assert set(payload["configs"]) == {"lexical_baseline", "bm25"}
    assert "dense" in payload["meta"]["skipped"]
    assert payload["configs"]["bm25"]["answerable"]["hit_at_1"] == 1.0
    assert (out / "t.md").exists()
