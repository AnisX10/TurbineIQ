# Assistant retrieval benchmark (roadmap step 3, WP6)

Step 3 asks for a corpus of public documents, a benchmark written before the retrieval
upgrade, a baseline run on the current lexical retriever, and an improved run with dense
retrieval and reranking, both committed as evidence. This page records what exists and what
does not.

## Status

| Item | State |
| --- | --- |
| Retrievers: shipped lexical baseline, indexed BM25, dense (sentence embeddings), reciprocal-rank fusion, cross-encoder reranking (`rag/hybrid.py`) | Done and tested. The model-backed classes have now been run against real weights (`BAAI/bge-m3`, `BAAI/bge-reranker-v2-m3`). |
| Benchmark format, relevance rules, metrics, report writer (`rag/evaluation.py`, `scripts/run_retrieval_benchmark.py`) | Done and tested against hand-computed metrics. |
| Corpus: 16 public documents (`data/corpus/manifest.json`) | Done. Source URL, licence and SHA-256 for each. The PDFs themselves are git-ignored and not committed. |
| Questions (`data/benchmark/questions.jsonl`) | Done: 88 questions, committed (2704998) before any retrieval run. |
| Baseline report (`docs/evidence/retrieval/baseline.md`, `.json`) | Done, measured (d79ab28). |
| Improved report, bge-m3 + bge-reranker-v2-m3 (`docs/evidence/retrieval/improved.md`, `.json`) | Done, measured (ccb4e06). |
| Cheaper configuration, bge-small-en-v1.5 + bge-reranker-v2-m3 (`docs/evidence/retrieval/improved-bge-small.md`, `.json`) | Done, measured. See [Cheaper embedding model](#cheaper-embedding-model-bge-small-en-v15). |

The corpus, questions and runs were produced on the author's laptop (Intel i5-1235U, CPU only)
because the cloud sessions could not reach ntrs.nasa.gov, arxiv.org or huggingface.co.
www.osti.gov timed out from that laptop as well, so there are no OSTI documents.

## Corpus

16 documents: 9 NASA NTRS reports (US-government works, public use permitted) and 7 arXiv
papers. 3 arXiv papers carry only arXiv's non-exclusive distribution licence and are marked not
redistributable; they are indexed from a local copy only.

| Id | Title (year) | Licence | Redistributable |
| --- | --- | --- | --- |
| `arxiv-1111.0233` | Gas turbine diagnostic system (2011) | arXiv non-exclusive distribution licence 1.0 | no |
| `arxiv-2104.14842` | A Thermodynamic based and Data Driven Hybrid Network for Gas Turbine Modeling (2021) | CC BY-SA 4.0 | yes |
| `arxiv-2209.09168` | Application of Neural Network in the Prediction of NOx Emissions from Degrading Gas Turbine (2022) | CC BY 4.0 | yes |
| `arxiv-2406.07572` | Domain-specific ReAct for physics-integrated iterative modeling: A case study of LLM agents for gas path analysis of gas turbines (2024) | arXiv non-exclusive distribution licence 1.0 | no |
| `arxiv-2506.19503` | Physics-Informed Neural Networks for Industrial Gas Turbines: Recent Trends, Advancements and Challenges (2025) | arXiv non-exclusive distribution licence 1.0 | no |
| `arxiv-2507.08697` | Domain-Informed Operation Excellence of Gas Turbine System with Machine Learning (2025) | CC BY 4.0 | yes |
| `arxiv-2606.26710` | Kalman Prototypical Networks for Few-shot Fault Detection in Combined Cycle Gas Turbines (2026) | CC BY 4.0 | yes |
| `ntrs-19780019107` | JT9D jet engine performance deterioration (1978) | NTRS GOV_PUBLIC_USE_PERMITTED | yes |
| `ntrs-19840004098` | A generalized computer code for developing dynamic gas turbine engine models (DIGTEM) (1983) | NTRS GOV_PUBLIC_USE_PERMITTED | yes |
| `ntrs-19860013216` | Ceramic thermal barrier coatings for electric utility gas turbine engines (1986) | NTRS GOV_PUBLIC_USE_PERMITTED | yes |
| `ntrs-20030003697` | Turbine Engine Clearance Control Systems: Current Practices and Future Directions (2002) | NTRS PUBLIC_USE_PERMITTED | yes |
| `ntrs-20070034949` | User's Guide for the Commercial Modular Aero-Propulsion System Simulation (C-MAPSS) (2007) | NTRS PUBLIC_USE_PERMITTED | yes |
| `ntrs-20100024368` | An Integrated Architecture for On-Board Aircraft Engine Performance Trend Monitoring and Gas Path Fault Diagnostics (2010) | NTRS GOV_PUBLIC_USE_PERMITTED | yes |
| `ntrs-20100029602` | Sensor and Actuator Needs for More Intelligent Gas Turbine Engines (2010) | NTRS PUBLIC_USE_PERMITTED | yes |
| `ntrs-20160001158` | Sensor Selection for Aircraft Engine Performance Estimation and Gas Path Fault Diagnostics (2016) | NTRS PUBLIC_USE_PERMITTED | yes |
| `ntrs-20160012485` | Practical Techniques for Modeling Gas Turbine Engine Performance (2016) | NTRS PUBLIC_USE_PERMITTED | yes |

Chunking: 900 characters with 120 overlap, 1160 chunks.

## Questions

88 questions written from the extracted document text before any configuration was run:
25 `factual_document`, 25 `numeric_document`, 26 `conceptual`, 12 `unanswerable`. Every gold
evidence phrase matched at least one chunk (the runner checks this). No question or label was
changed after seeing results.

## Results (measured)

Answerable questions: 76. Unanswerable: 12. 95% intervals are seeded bootstrap over questions.
Wall time for the whole improved run (embedding 1160 chunks with bge-m3, then all five
configurations including reranking 30 candidates per question): 5107 s on the i5-1235U CPU;
embedding alone took about 25 minutes.

| Configuration | Hit@1 | Hit@3 [95% CI] | Hit@10 | MRR@10 [95% CI] | Context recall@3 | Refusal AUC |
| --- | --- | --- | --- | --- | --- | --- |
| lexical_baseline (shipped) | 0.579 | 0.763 [0.671, 0.855] | 0.947 | 0.698 [0.611, 0.774] | 0.763 | 0.917 |
| bm25 | 0.579 | 0.763 [0.671, 0.855] | 0.947 | 0.698 [0.611, 0.774] | 0.763 | 0.917 |
| dense (bge-m3) | 0.566 | 0.776 [0.684, 0.868] | 0.895 | 0.671 [0.579, 0.753] | 0.776 | 0.995 |
| hybrid (BM25 + dense, RRF) | 0.632 | 0.763 [0.671, 0.855] | 0.974 | 0.724 [0.638, 0.802] | 0.763 | 0.967 |
| hybrid_rerank (+ bge-reranker-v2-m3) | 0.763 | 0.921 [0.855, 0.974] | 0.987 | 0.851 [0.785, 0.911] | 0.908 | 1.000 |

Hit@3 / MRR@10 by category:

| Configuration | conceptual (n=26) | factual_document (n=25) | numeric_document (n=25) |
| --- | --- | --- | --- |
| lexical_baseline | 0.808 / 0.725 | 0.800 / 0.768 | 0.680 / 0.598 |
| dense | 0.731 / 0.644 | 0.840 / 0.698 | 0.760 / 0.673 |
| hybrid | 0.731 / 0.709 | 0.800 / 0.763 | 0.760 / 0.700 |
| hybrid_rerank | 0.923 / 0.833 | 0.920 / 0.898 | 0.920 / 0.821 |

Full reports: `docs/evidence/retrieval/baseline.md` and `improved.md` (with JSON).

### Cheaper embedding model (bge-small-en-v1.5)

Same corpus, questions, chunking and reranker (`BAAI/bge-reranker-v2-m3`), with
`--embedding-model BAAI/bge-small-en-v1.5 --query-prefix "Represent this sentence for
searching relevant passages: "`. Wall time for the whole run (all five configurations):
4044 s on the same i5-1235U CPU. Embedding the 1160 chunks took about 2.5 minutes (bge-m3:
about 25 minutes); nearly all the remaining time is the reranker. The lexical rows are
identical to the table above and are omitted here. The report records `git_commit 5493638`, a
local commit that changed only this page and was not pushed; code, corpus and questions were
the same as at `ccb4e06`.

| Configuration | Hit@1 | Hit@3 [95% CI] | Hit@10 | MRR@10 [95% CI] | Context recall@3 | Refusal AUC |
| --- | --- | --- | --- | --- | --- | --- |
| dense (bge-small) | 0.303 | 0.645 [0.526, 0.750] | 0.895 | 0.494 [0.416, 0.576] | 0.651 | 0.979 |
| hybrid (BM25 + bge-small, RRF) | 0.487 | 0.776 [0.684, 0.868] | 0.974 | 0.652 [0.572, 0.728] | 0.776 | 0.827 |
| hybrid_rerank (+ bge-reranker-v2-m3) | 0.763 | 0.908 [0.829, 0.961] | 0.987 | 0.850 [0.783, 0.911] | 0.895 | 1.000 |

Full report: `docs/evidence/retrieval/improved-bge-small.md` (with JSON).

## What the numbers support (interpretation)

- Hybrid retrieval with cross-encoder reranking is the only configuration that clearly beats the
  shipped retriever: Hit@3 0.763 to 0.921 and MRR@10 0.698 to 0.851. The intervals are
  unpaired and touch at 0.855 for Hit@3; the MRR intervals do not overlap. A paired test over
  the same questions was not computed (per-question results are not stored in the report).
- Dense retrieval alone and fusion without reranking are not better than the baseline on this
  benchmark; the gain comes from the reranker.
- `bm25` is identical to `lexical_baseline` by construction: it is an indexed copy of the
  shipped scoring with the same tokenizer and constants, included to check that equivalence and
  as the lexical half of `hybrid`. It is not a separate method.
- Numeric questions gain the most (Hit@3 0.680 to 0.920).
- Refusal AUC of 1.000 for `hybrid_rerank` means its top score separated all 12 unanswerable
  questions from the answerable ones here. With 12 questions this is weak evidence, and the
  score threshold for refusing has not been chosen or tested.
- Cost: reranking with a 568M-parameter cross-encoder on a laptop CPU is slow (the full run took
  85 minutes). Per-query latency was not measured separately; it must be before the assistant
  uses this configuration interactively.

## Limitations

- Retrieval metrics only. They do not show that a language model answers correctly, that
  numbers in answers are faithful (PR #5), or that generated citations are right.
- Questions and gold labels were written by the same agent that built the retrievers, from the
  same documents, without independent review. Question wording may favour lexical overlap.
- Small benchmark (76 answerable, 12 unanswerable); intervals are wide.
- The corpus leans towards aero-engine NASA reports and ML papers; there is little on
  heavy-duty industrial units like the 6B.03, and no OEM documents.
- One run per configuration; the timing is a single wall-clock measurement on one machine.

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
