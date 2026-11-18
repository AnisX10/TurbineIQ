# Retrieval benchmark: baseline

- **date_utc:** 2026-11-17 12:26
- **git_commit:** 2704998
- **questions:** 88
- **corpus_files:** 16
- **chunks:** 1160
- **chunking:** 900 characters, 120 overlap
- **embedding_model:** not used / unavailable
- **reranker_model:** not used
- **skipped:** none

Retrieval metrics only: they measure whether the evidence is found, not whether a language model answers correctly. 95% intervals are seeded bootstrap over questions.

| Configuration | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR@10 | Context recall@3 | Refusal AUC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lexical_baseline | 0.579 | 0.763 [0.671, 0.855] | 0.868 | 0.947 | 0.698 | 0.763 | 0.917 |

## By category (Hit@3 / MRR@10)

| Configuration | conceptual | factual_document | numeric_document |
| --- | --- | --- | --- |
| lexical_baseline | 0.808 / 0.725 (n=26) | 0.800 / 0.768 (n=25) | 0.680 / 0.598 (n=25) |
