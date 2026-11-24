"""Optional local cross-encoder reranker (ONNX on CPU via fastembed).

Install with ``pip install -e ".[rerank]"``. The model is downloaded once from Hugging Face
on first use and cached; after that it runs offline. Nothing here sends queries or passages
anywhere: scoring happens in this process.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import replace

from .retrieval import SearchHit

DEFAULT_RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
RERANK_ENV = "TURBINEIQ_RERANK_MODEL"
_LOG = logging.getLogger(__name__)


class RerankerUnavailable(RuntimeError):
    """The rerank extra is not installed or the model could not be loaded."""


class CrossEncoderReranker:
    def __init__(self, model: str = DEFAULT_RERANK_MODEL, *, cache_dir: str | None = None) -> None:
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
        except ImportError as exc:  # pragma: no cover - depends on the optional extra
            raise RerankerUnavailable(
                'reranking needs the optional extra: pip install -e ".[rerank]"'
            ) from exc
        try:
            self._encoder = TextCrossEncoder(model_name=model, cache_dir=cache_dir)
        except Exception as exc:  # pragma: no cover - network or model errors
            raise RerankerUnavailable(f"could not load reranker {model}: {exc}") from exc
        self.name = model

    def rerank(self, query: str, hits: list[SearchHit]) -> list[SearchHit]:
        if not hits:
            return []
        passages = [_passage(hit) for hit in hits]
        scores = list(self._encoder.rerank(query, passages))
        rescored = [
            replace(hit, score=1 / (1 + math.exp(-float(score))))  # logit -> 0..1
            for hit, score in zip(hits, scores, strict=True)
        ]
        # Ties keep the lexical order, which is itself deterministic.
        order = sorted(range(len(rescored)), key=lambda i: (-rescored[i].score, i))
        return [rescored[i] for i in order]


def _passage(hit: SearchHit) -> str:
    if hit.chunk.section:
        return f"{hit.chunk.section}. {hit.chunk.text}"
    return hit.chunk.text


def reranker_from_env() -> CrossEncoderReranker | None:
    """Build the reranker named by TURBINEIQ_RERANK_MODEL, or None (lexical only).

    Unset, empty or "off" keeps plain lexical search. "default" picks DEFAULT_RERANK_MODEL.
    If the extra or the model is missing, log a warning and fall back to lexical search.
    """

    model = os.environ.get(RERANK_ENV, "").strip()
    if not model or model.lower() in {"off", "0", "false", "none"}:
        return None
    if model.lower() in {"default", "on", "1", "true"}:
        model = DEFAULT_RERANK_MODEL
    try:
        return CrossEncoderReranker(model)
    except RerankerUnavailable as exc:
        _LOG.warning("Reranker disabled, using lexical search only: %s", exc)
        return None
