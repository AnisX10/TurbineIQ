"""Score evidence retrieval on tests/data/retrieval_eval.json.

    PYTHONPATH=src python scripts/eval_retrieval.py                  # lexical only
    PYTHONPATH=src python scripts/eval_retrieval.py --rerank default # + cross-encoder

--rerank needs the `rerank` extra and downloads the model on first use.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from turbineiq.rag.evaluation import evaluate, load_eval_set
from turbineiq.rag.rerank import DEFAULT_RERANK_MODEL, CrossEncoderReranker
from turbineiq.rag.retrieval import search_documents

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--rerank",
        action="append",
        default=[],
        metavar="MODEL",
        help="cross-encoder model to compare ('default' = %s)" % DEFAULT_RERANK_MODEL,
    )
    parser.add_argument("--misses", action="store_true", help="list missed questions")
    args = parser.parse_args()

    questions, chunks = load_eval_set(ROOT / "tests/data/retrieval_eval.json", ROOT)
    print(f"{len(questions)} questions over {len(chunks)} chunks\n")
    models = [None] + [DEFAULT_RERANK_MODEL if m == "default" else m for m in args.rerank]

    print(f"{'mode':55} {'hit@1':>6} {'hit@4':>6} {'MRR@4':>6} {'ms/query':>9}")
    for model in models:
        # One model in memory at a time: several large ones together exhaust RAM.
        reranker = None if model is None else CrossEncoderReranker(model)
        name = "lexical" if model is None else f"lexical + {model}"
        if reranker is not None:
            search_documents("warm up", chunks, reranker=reranker)  # load the model first

        def search(query, docs, k, _r=reranker):
            return search_documents(query, docs, top_k=k, reranker=_r)

        at1 = evaluate(search, questions, chunks, top_k=1)
        at4 = evaluate(search, questions, chunks, top_k=4)
        print(
            f"{name:55} {at1.hit_rate:6.3f} {at4.hit_rate:6.3f} {at4.mrr:6.3f}"
            f" {at4.mean_latency_ms:9.1f}"
        )
        if args.misses:
            for miss in at4.misses:
                print(f"    missed: {miss}")


if __name__ == "__main__":
    main()
