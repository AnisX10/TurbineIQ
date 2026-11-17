"""Run the retrieval benchmark on a local corpus and write JSON and Markdown reports.

    python scripts/run_retrieval_benchmark.py --label baseline --configs lexical_baseline
    python scripts/run_retrieval_benchmark.py --label improved \
        --configs lexical_baseline,bm25,dense,hybrid,hybrid_rerank

A configuration whose model cannot be loaded (no network, no weights, extra not installed)
is reported as skipped with the reason; nothing is substituted for it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
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
from turbineiq.rag.evaluation import (  # noqa: E402
    check_gold_in_corpus,
    evaluate,
    load_benchmark,
    render_markdown,
    summarize,
)
from turbineiq.rag.hybrid import (  # noqa: E402
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RERANKER_MODEL,
    CrossEncoderReranker,
    SentenceTransformerEmbedder,
)

ALL_CONFIGS = ("lexical_baseline", "bm25", "dense", "hybrid", "hybrid_rerank")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus-dir", type=Path, default=ROOT / "data/corpus/files")
    parser.add_argument("--benchmark", type=Path, default=ROOT / "data/benchmark/questions.jsonl")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs/evidence/retrieval")
    parser.add_argument("--label", default="run", help="output name, e.g. baseline or improved")
    parser.add_argument("--configs", default=",".join(ALL_CONFIGS))
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER_MODEL)
    parser.add_argument("--query-prefix", default="", help="prefix for queries (model specific)")
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--candidate-k", type=int, default=30)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/corpus/.cache")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    files = sorted(
        p for p in args.corpus_dir.glob("*") if p.suffix.lower() in {".pdf", ".md", ".txt"}
    )
    if not files:
        print(f"no corpus files in {args.corpus_dir}", file=sys.stderr)
        return 2
    chunks = []
    for path in files:
        chunks.extend(load_document_path(path, chunk_size=args.chunk_size, overlap=args.overlap))
    questions = load_benchmark(args.benchmark)
    problems = check_gold_in_corpus(questions, chunks)
    if problems:
        print("benchmark gold not found in corpus:", *problems, sep="\n  ", file=sys.stderr)
        return 3

    wanted = [c.strip() for c in args.configs.split(",") if c.strip()]
    unknown = set(wanted) - set(ALL_CONFIGS)
    if unknown:
        print(f"unknown configs: {sorted(unknown)}", file=sys.stderr)
        return 2

    bm25 = Bm25Retriever(chunks)
    built: dict[str, object] = {"lexical_baseline": LexicalBaseline(chunks), "bm25": bm25}
    skipped: dict[str, str] = {}
    dense = None
    if {"dense", "hybrid", "hybrid_rerank"} & set(wanted):
        try:
            embedder = SentenceTransformerEmbedder(
                args.embedding_model, query_prefix=args.query_prefix
            )
            dense = DenseRetriever(chunks, embedder, cache_dir=args.cache_dir)
            built["dense"] = dense
            built["hybrid"] = HybridRetriever([bm25, dense], candidate_k=args.candidate_k)
        except Exception as exc:  # model missing, offline, extra not installed
            reason = f"embedding model unavailable: {type(exc).__name__}: {exc}"
            skipped.update({name: reason for name in ("dense", "hybrid", "hybrid_rerank")})
    if "hybrid_rerank" in wanted and "hybrid" in built:
        try:
            reranker = CrossEncoderReranker(args.reranker_model)
            built["hybrid_rerank"] = RerankedRetriever(
                built["hybrid"], reranker, candidate_k=args.candidate_k
            )
        except Exception as exc:
            skipped["hybrid_rerank"] = f"reranker unavailable: {type(exc).__name__}: {exc}"

    reports: dict[str, dict] = {}
    for name in wanted:
        if name in skipped:
            print(f"skipped {name}: {skipped[name]}")
            continue
        reports[name] = summarize(evaluate(built[name], questions), seed=args.seed)
        a = reports[name]["answerable"]
        print(f"{name}: hit@3={a['hit_at_3']:.3f} mrr@10={a['mrr_at_10']:.3f}")

    meta = {
        "date_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        "git_commit": _git_commit(),
        "questions": len(questions),
        "corpus_files": len(files),
        "chunks": len(chunks),
        "chunking": f"{args.chunk_size} characters, {args.overlap} overlap",
        "embedding_model": args.embedding_model if dense else "not used / unavailable",
        "reranker_model": args.reranker_model if "hybrid_rerank" in reports else "not used",
        "skipped": skipped or "none",
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": meta,
        "corpus": [{"file": p.name, "sha256": _sha256(p)} for p in files],
        "configs": reports,
    }
    (args.out_dir / f"{args.label}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.out_dir / f"{args.label}.md").write_text(
        render_markdown(f"Retrieval benchmark: {args.label}", reports, meta), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
