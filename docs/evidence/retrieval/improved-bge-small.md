# Retrieval benchmark: improved-bge-small

- **date_utc:** 2026-11-17 17:20
- **git_commit:** 5493638
- **questions:** 88
- **corpus_files:** 16
- **chunks:** 1160
- **chunking:** 900 characters, 120 overlap
- **embedding_model:** BAAI/bge-small-en-v1.5
- **reranker_model:** BAAI/bge-reranker-v2-m3
- **skipped:** none

Retrieval metrics only: they measure whether the evidence is found, not whether a language model answers correctly. 95% intervals are seeded bootstrap over questions.

| Configuration | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR@10 | Context recall@3 | Refusal AUC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lexical_baseline | 0.579 | 0.763 [0.671, 0.855] | 0.868 | 0.947 | 0.698 | 0.763 | 0.917 |
| bm25 | 0.579 | 0.763 [0.671, 0.855] | 0.868 | 0.947 | 0.698 | 0.763 | 0.917 |
| dense | 0.303 | 0.645 [0.526, 0.750] | 0.789 | 0.895 | 0.494 | 0.651 | 0.979 |
| hybrid | 0.487 | 0.776 [0.684, 0.868] | 0.882 | 0.974 | 0.652 | 0.776 | 0.827 |
| hybrid_rerank | 0.763 | 0.908 [0.829, 0.961] | 0.987 | 0.987 | 0.850 | 0.895 | 1.000 |

## By category (Hit@3 / MRR@10)

| Configuration | conceptual | factual_document | numeric_document |
| --- | --- | --- | --- |
| lexical_baseline | 0.808 / 0.725 (n=26) | 0.800 / 0.768 (n=25) | 0.680 / 0.598 (n=25) |
| bm25 | 0.808 / 0.725 (n=26) | 0.800 / 0.768 (n=25) | 0.680 / 0.598 (n=25) |
| dense | 0.654 / 0.482 (n=26) | 0.640 / 0.491 (n=25) | 0.640 / 0.508 (n=25) |
| hybrid | 0.846 / 0.660 (n=26) | 0.760 / 0.676 (n=25) | 0.720 / 0.621 (n=25) |
| hybrid_rerank | 0.923 / 0.833 (n=26) | 0.920 / 0.898 (n=25) | 0.880 / 0.818 (n=25) |
