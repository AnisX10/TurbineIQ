# Retrieval benchmark: improved

- **date_utc:** 2026-11-17 16:12
- **git_commit:** d79ab28
- **questions:** 88
- **corpus_files:** 16
- **chunks:** 1160
- **chunking:** 900 characters, 120 overlap
- **embedding_model:** BAAI/bge-m3
- **reranker_model:** BAAI/bge-reranker-v2-m3
- **skipped:** none

Retrieval metrics only: they measure whether the evidence is found, not whether a language model answers correctly. 95% intervals are seeded bootstrap over questions.

| Configuration | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR@10 | Context recall@3 | Refusal AUC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lexical_baseline | 0.579 | 0.763 [0.671, 0.855] | 0.868 | 0.947 | 0.698 | 0.763 | 0.917 |
| bm25 | 0.579 | 0.763 [0.671, 0.855] | 0.868 | 0.947 | 0.698 | 0.763 | 0.917 |
| dense | 0.566 | 0.776 [0.684, 0.868] | 0.803 | 0.895 | 0.671 | 0.776 | 0.995 |
| hybrid | 0.632 | 0.763 [0.671, 0.855] | 0.855 | 0.974 | 0.724 | 0.763 | 0.967 |
| hybrid_rerank | 0.763 | 0.921 [0.855, 0.974] | 0.987 | 0.987 | 0.851 | 0.908 | 1.000 |

## By category (Hit@3 / MRR@10)

| Configuration | conceptual | factual_document | numeric_document |
| --- | --- | --- | --- |
| lexical_baseline | 0.808 / 0.725 (n=26) | 0.800 / 0.768 (n=25) | 0.680 / 0.598 (n=25) |
| bm25 | 0.808 / 0.725 (n=26) | 0.800 / 0.768 (n=25) | 0.680 / 0.598 (n=25) |
| dense | 0.731 / 0.644 (n=26) | 0.840 / 0.698 (n=25) | 0.760 / 0.673 (n=25) |
| hybrid | 0.731 / 0.709 (n=26) | 0.800 / 0.763 (n=25) | 0.760 / 0.700 (n=25) |
| hybrid_rerank | 0.923 / 0.833 (n=26) | 0.920 / 0.898 (n=25) | 0.920 / 0.821 (n=25) |
