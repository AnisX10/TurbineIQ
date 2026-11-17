"""Retrievers for the assistant benchmark: BM25, dense, rank fusion and reranking.

``search_documents`` in :mod:`turbineiq.rag.retrieval` stays the baseline. The classes here
add what the roadmap (WP6) calls for, behind one small interface so the benchmark can
compare configurations on the same chunks:

* :class:`Bm25Retriever` scores exactly like ``search_documents`` but indexes once;
* :class:`DenseRetriever` ranks by cosine similarity of sentence embeddings;
* :class:`HybridRetriever` fuses rankings with reciprocal-rank fusion (Cormack et al., 2009);
* :class:`RerankedRetriever` re-orders a candidate list with a cross-encoder.

Embedding and reranking models are optional (``pip install '.[retrieval]'``) and are only
imported when :class:`SentenceTransformerEmbedder` or :class:`CrossEncoderReranker` is built.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np

from .documents import DocumentChunk
from .retrieval import SearchHit, _tokens, search_documents

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


class Retriever(Protocol):
    """Anything that returns ranked chunks for a query."""

    def search(self, query: str, top_k: int = 4) -> list[SearchHit]: ...


class Embedder(Protocol):
    """Maps texts to row vectors. ``is_query`` lets asymmetric models add a query prefix."""

    name: str

    def embed(self, texts: Sequence[str], *, is_query: bool) -> np.ndarray: ...


class Reranker(Protocol):
    """Scores (query, passage) pairs; higher is more relevant."""

    name: str

    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


def _check_top_k(top_k: int) -> None:
    if not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be an integer of at least 1")


def _ranked(
    chunks: Sequence[DocumentChunk], scores: Sequence[float], top_k: int
) -> list[SearchHit]:
    order = sorted(
        range(len(chunks)),
        key=lambda i: (-scores[i], chunks[i].source, chunks[i].chunk_index),
    )
    return [SearchHit(chunk=chunks[i], score=float(scores[i])) for i in order[:top_k]]


class LexicalBaseline:
    """The shipped retriever, unchanged: ``search_documents`` re-indexes on every query."""

    name = "lexical_baseline"

    def __init__(self, chunks: Sequence[DocumentChunk]) -> None:
        self._chunks = list(chunks)

    def search(self, query: str, top_k: int = 4) -> list[SearchHit]:
        return search_documents(query, self._chunks, top_k=top_k)


class Bm25Retriever:
    """BM25 with the same tokenizer, constants and ordering as ``search_documents``."""

    name = "bm25"

    def __init__(self, chunks: Sequence[DocumentChunk], *, k1: float = 1.2, b: float = 0.75):
        self._chunks = list(chunks)
        self._k1, self._b = k1, b
        self._tf: list[dict[str, int]] = []
        self._len: list[int] = []
        self._df: dict[str, int] = {}
        for chunk in self._chunks:
            tokens = _tokens(chunk.text)
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            self._tf.append(counts)
            self._len.append(len(tokens))
            for token in counts:
                self._df[token] = self._df.get(token, 0) + 1
        self._avg = sum(self._len) / max(len(self._len), 1)

    def search(self, query: str, top_k: int = 4) -> list[SearchHit]:
        _check_top_k(top_k)
        terms = set(_tokens(query))
        if not terms or not self._chunks:
            return []
        n = len(self._chunks)
        scores = [0.0] * n
        for term in terms:
            df = self._df.get(term, 0)
            if not df:
                continue
            idf = math.log1p((n - df + 0.5) / (df + 0.5))
            for i, counts in enumerate(self._tf):
                tf = counts.get(term, 0)
                if tf:
                    denom = tf + self._k1 * (
                        1 - self._b + self._b * self._len[i] / max(self._avg, 1)
                    )
                    scores[i] += idf * tf * (self._k1 + 1) / denom
        hits = [i for i in range(n) if scores[i] > 0]
        order = sorted(
            hits, key=lambda i: (-scores[i], self._chunks[i].source, self._chunks[i].chunk_index)
        )
        return [SearchHit(chunk=self._chunks[i], score=scores[i]) for i in order[:top_k]]


class DenseRetriever:
    """Cosine-similarity search over sentence embeddings held in memory (NumPy)."""

    def __init__(
        self,
        chunks: Sequence[DocumentChunk],
        embedder: Embedder,
        *,
        cache_dir: str | Path | None = None,
        batch_size: int = 32,
    ) -> None:
        self._chunks = list(chunks)
        self._embedder = embedder
        self.name = f"dense:{embedder.name}"
        texts = [chunk.text for chunk in self._chunks]
        self._matrix = self._load_or_embed(texts, cache_dir, batch_size)

    def _load_or_embed(self, texts: list[str], cache_dir: str | Path | None, batch: int):
        path = None
        if cache_dir is not None:
            digest = hashlib.sha256(
                "\x00".join([self._embedder.name, *texts]).encode("utf-8")
            ).hexdigest()[:24]
            path = Path(cache_dir) / f"embeddings-{digest}.npy"
            if path.exists():
                return np.load(path)
        parts = [
            self._embedder.embed(texts[i : i + batch], is_query=False)
            for i in range(0, len(texts), batch)
        ]
        matrix = np.vstack(parts) if parts else np.zeros((0, 1), dtype=np.float32)
        matrix = _normalise(matrix)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, matrix)
        return matrix

    def search(self, query: str, top_k: int = 4) -> list[SearchHit]:
        _check_top_k(top_k)
        if not query.strip() or not len(self._chunks):
            return []
        q = _normalise(self._embedder.embed([query], is_query=True))[0]
        scores = self._matrix @ q
        return _ranked(self._chunks, scores.tolist(), top_k)


def _normalise(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1.0, norms)


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[SearchHit]], *, k: int = 60
) -> list[SearchHit]:
    """Fuse ranked lists: score(d) = sum over lists of 1 / (k + rank(d)), rank from 1."""

    if k < 1:
        raise ValueError("k must be at least 1")
    fused: dict[tuple[str, int], float] = {}
    chunks: dict[tuple[str, int], DocumentChunk] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            key = (hit.chunk.source, hit.chunk.chunk_index)
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank)
            chunks[key] = hit.chunk
    order = sorted(fused, key=lambda key: (-fused[key], key[0], key[1]))
    return [SearchHit(chunk=chunks[key], score=fused[key]) for key in order]


class HybridRetriever:
    """Reciprocal-rank fusion of several retrievers' candidate lists."""

    def __init__(
        self,
        retrievers: Sequence[Retriever],
        *,
        candidate_k: int = 50,
        rrf_k: int = 60,
        name: str = "hybrid",
    ) -> None:
        if not retrievers:
            raise ValueError("at least one retriever is required")
        self._retrievers = list(retrievers)
        self._candidate_k = candidate_k
        self._rrf_k = rrf_k
        self.name = name

    def search(self, query: str, top_k: int = 4) -> list[SearchHit]:
        _check_top_k(top_k)
        lists = [r.search(query, max(self._candidate_k, top_k)) for r in self._retrievers]
        return reciprocal_rank_fusion(lists, k=self._rrf_k)[:top_k]


class RerankedRetriever:
    """Retrieve ``candidate_k`` chunks, then order them by a cross-encoder score."""

    def __init__(self, base: Retriever, reranker: Reranker, *, candidate_k: int = 30) -> None:
        self._base = base
        self._reranker = reranker
        self._candidate_k = candidate_k
        self.name = f"{getattr(base, 'name', 'retriever')}+rerank:{reranker.name}"

    def search(self, query: str, top_k: int = 4) -> list[SearchHit]:
        _check_top_k(top_k)
        candidates = self._base.search(query, max(self._candidate_k, top_k))
        if not candidates:
            return []
        scores = self._reranker.score(query, [hit.chunk.text for hit in candidates])
        order = sorted(
            range(len(candidates)),
            key=lambda i: (-scores[i], candidates[i].chunk.source, candidates[i].chunk.chunk_index),
        )
        return [SearchHit(chunk=candidates[i].chunk, score=float(scores[i])) for i in order[:top_k]]


class SentenceTransformerEmbedder:
    """Local embedding model via ``sentence-transformers`` (optional ``retrieval`` extra)."""

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        *,
        query_prefix: str = "",
        document_prefix: str = "",
        device: str | None = None,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on the optional extra
            raise RuntimeError(
                "sentence-transformers is not installed; run `pip install -e '.[retrieval]'`"
            ) from exc
        self.name = model_name
        self._model = SentenceTransformer(model_name, device=device)
        self._query_prefix = query_prefix
        self._document_prefix = document_prefix

    def embed(self, texts: Sequence[str], *, is_query: bool) -> np.ndarray:
        prefix = self._query_prefix if is_query else self._document_prefix
        return np.asarray(
            self._model.encode(
                [prefix + t for t in texts], normalize_embeddings=True, show_progress_bar=False
            ),
            dtype=np.float32,
        )


class CrossEncoderReranker:
    """Cross-encoder reranker via ``sentence-transformers`` (optional ``retrieval`` extra)."""

    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL, *, device: str | None = None):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - depends on the optional extra
            raise RuntimeError(
                "sentence-transformers is not installed; run `pip install -e '.[retrieval]'`"
            ) from exc
        self.name = model_name
        self._model = CrossEncoder(model_name, device=device)

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        scores = self._model.predict([(query, p) for p in passages], show_progress_bar=False)
        return [float(s) for s in scores]
