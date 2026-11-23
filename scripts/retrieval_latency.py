"""Measure per-query retrieval latency on the local corpus and write a JSON report.

    python scripts/retrieval_latency.py --embedding-model BAAI/bge-m3 --label latency-bge-m3

Times each configuration over the first --queries benchmark questions after one warm-up query.
Chunk embeddings come from the benchmark's cache, so only query-time work is timed: query
embedding, search, fusion and reranking. Index building and model loading are reported
separately and are not part of the per-query figures.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from turbineiq.rag import (  # noqa: E402
    Bm25Retriever,
    DenseRetriever,
    HybridRetriever,
    LexicalBaseline,
    RerankedRetriever,
    load_document_path,
)
from turbineiq.rag.evaluation import load_benchmark  # noqa: E402
from turbineiq.rag.hybrid import (  # noqa: E402
    DEFAULT_RERANKER_MODEL,
    CrossEncoderReranker,
    SentenceTransformerEmbedder,
)


def _time_queries(retriever, queries: list[str], top_k: int) -> dict:
    retriever.search(queries[0], top_k=top_k)  # warm-up, not timed
    times = []
    for query in queries:
        start = time.perf_counter()
        retriever.search(query, top_k=top_k)
        times.append(time.perf_counter() - start)
    return {
        "queries": len(times),
        "median_s": statistics.median(times),
        "mean_s": statistics.fmean(times),
        "max_s": max(times),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus-dir", type=Path, default=ROOT / "data/corpus/files")
    parser.add_argument("--benchmark", type=Path, default=ROOT / "data/benchmark/questions.jsonl")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs/evidence/retrieval")
    parser.add_argument("--label", default="latency")
    parser.add_argument("--embedding-model", required=True)
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER_MODEL)
    parser.add_argument("--query-prefix", default="")
    parser.add_argument("--queries", type=int, default=10)
    parser.add_argument("--candidate-k", default="30,10", help="comma-separated rerank depths")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/corpus/.cache")
    args = parser.parse_args()

    files = sorted(
        p for p in args.corpus_dir.glob("*") if p.suffix.lower() in {".pdf", ".md", ".txt"}
    )
    chunks = []
    for path in files:
        chunks.extend(load_document_path(path, chunk_size=900, overlap=120))
    queries = [q.question for q in load_benchmark(args.benchmark)][: args.queries]

    setup: dict[str, float] = {}
    start = time.perf_counter()
    bm25 = Bm25Retriever(chunks)
    setup["bm25_index_s"] = time.perf_counter() - start
    start = time.perf_counter()
    embedder = SentenceTransformerEmbedder(args.embedding_model, query_prefix=args.query_prefix)
    setup["embedding_model_load_s"] = time.perf_counter() - start
    start = time.perf_counter()
    dense = DenseRetriever(chunks, embedder, cache_dir=args.cache_dir)
    setup["dense_index_s (from cache if present)"] = time.perf_counter() - start
    start = time.perf_counter()
    reranker = CrossEncoderReranker(args.reranker_model)
    setup["reranker_load_s"] = time.perf_counter() - start

    results: dict[str, dict] = {
        "lexical_baseline": _time_queries(LexicalBaseline(chunks), queries, args.top_k),
        "bm25": _time_queries(bm25, queries, args.top_k),
        "dense": _time_queries(dense, queries, args.top_k),
    }
    for k in (int(v) for v in args.candidate_k.split(",")):
        hybrid = HybridRetriever([bm25, dense], candidate_k=k)
        if k == int(args.candidate_k.split(",")[0]):
            results["hybrid"] = _time_queries(hybrid, queries, args.top_k)
        reranked = RerankedRetriever(hybrid, reranker, candidate_k=k)
        results[f"hybrid_rerank (candidate_k={k})"] = _time_queries(reranked, queries, args.top_k)

    import torch  # noqa: PLC0415 - optional extra, imported only for the report

    payload = {
        "meta": {
            "embedding_model": args.embedding_model,
            "reranker_model": args.reranker_model,
            "chunks": len(chunks),
            "top_k": args.top_k,
            "machine": platform.processor() or platform.machine(),
            "cpu_count": os.cpu_count(),
            "torch": torch.__version__,
            "torch_threads": torch.get_num_threads(),
            "note": "Per-query wall time after one warm-up query; CPU only.",
        },
        "setup": setup,
        "per_query": results,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.label}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for name, r in results.items():
        print(f"{name}: median {r['median_s']:.3f} s, max {r['max_s']:.3f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
