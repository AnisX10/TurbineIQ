# Assistant retrieval benchmark (roadmap step 3, WP6)

Step 3 asks for a corpus of public documents, a benchmark written before the retrieval
upgrade, a baseline run on the current lexical retriever, and an improved run with dense
retrieval and reranking, both committed as evidence. This page records what exists and what
does not.

## Status

| Item | State |
| --- | --- |
| Retrievers: shipped lexical baseline, indexed BM25, dense (sentence embeddings), reciprocal-rank fusion, cross-encoder reranking (`rag/hybrid.py`) | Done and tested with small test doubles. The two model-backed classes (`SentenceTransformerEmbedder`, `CrossEncoderReranker`) have **not** been run against real model weights. |
| Benchmark format, relevance rules, metrics, report writer (`rag/evaluation.py`, `scripts/run_retrieval_benchmark.py`) | Done and tested against hand-computed metrics. |
| Corpus manifest and fetch/verify tool (`scripts/corpus_manifest.py`, `data/corpus/manifest.json`) | Tool done; the manifest is **empty**. |
| 10 to 20 public documents with source and licence notes | **Not done.** |
| Benchmark questions with reference evidence (`data/benchmark/questions.jsonl`) | **Not done.** They must be written from the real documents. |
| Baseline and improved reports in `docs/evidence/retrieval/` | **Not done.** No result is reported here because none has been measured. |

Blocker: the cloud session that built this could not reach the document sources
(ntrs.nasa.gov, osti.gov, arxiv.org) or the model host (huggingface.co); its network policy
returned 403. A personal "TurbineIQ" environment that allows those hosts has been created,
but a running session cannot move onto it, so the remaining work needs a new session on that
environment (or the documents supplied locally).

## How a question is judged

Each line of `data/benchmark/questions.jsonl` is JSON:

```json
{"id": "fact-001", "category": "factual_document", "question": "...", "answerable": true,
 "gold": [{"source": "GER-3567H.pdf", "pages": [5], "evidence": ["short phrase from the page"]}],
 "reference_answer": "..."}
```

Categories: `factual_document`, `numeric_document`, `conceptual`, and `unanswerable`
(questions the corpus cannot answer; `answerable` false, no gold). A retrieved chunk counts as
relevant when it comes from a gold source, from a gold page if pages are given, and contains
one of the gold evidence phrases (whitespace and case ignored). Phrases, not chunk ids, so
labels survive changing the chunk size. `scripts/run_retrieval_benchmark.py` refuses to run if
any gold passage matches no chunk, which catches label typos and extraction problems.

Metrics, per configuration, over answerable questions: Hit@1, 3, 5, 10 (a relevant chunk in
the top k), MRR@10, precision@3, context recall@3 (share of gold evidence phrases present in
the top three chunks), seeded bootstrap 95% intervals, and a per-category breakdown. For
unanswerable questions the report gives the AUC of the top retrieval score (how well the
score separates answerable from unanswerable questions; 0.5 is no signal). These are
retrieval metrics only. They do not show that a language model answers correctly, that
numbers in answers are faithful (PR #5 covers numeric traceability), or that citations in
generated text are right. Those need the model-in-the-loop runs listed in WP6.

## Running it

```bash
python -m pip install -e '.[retrieval]'          # sentence-transformers and torch
python scripts/corpus_manifest.py fetch --update  # after filling data/corpus/manifest.json
python scripts/run_retrieval_benchmark.py --label baseline --configs lexical_baseline
python scripts/run_retrieval_benchmark.py --label improved \
    --configs lexical_baseline,bm25,dense,hybrid,hybrid_rerank
```

Default models follow the roadmap: `BAAI/bge-m3` embeddings and `BAAI/bge-reranker-v2-m3`.
Both are large for a CPU; `--embedding-model BAAI/bge-small-en-v1.5 --query-prefix
"Represent this sentence for searching relevant passages: "` is a cheaper first run. A
configuration whose model cannot be loaded is written to the report as skipped with the
reason; nothing stands in for it.

## Rules for the benchmark

1. Write the questions and evidence before running any retrieval configuration, and do not
   edit them after seeing results except to fix a label that is plainly wrong (and say so).
2. Report the baseline and every configuration tried, not only the best.
3. Only public documents. Copyrighted or paywalled documents may be indexed locally from the
   author's own copy but must not be committed; set `redistributable` accordingly in the
   manifest. Leaked or confidential manuals stay excluded (`GE_6B03_PUBLIC_DATA_REVIEW.md`).
