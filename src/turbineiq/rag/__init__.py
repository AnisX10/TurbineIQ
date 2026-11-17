"""Local technical-document ingestion, search, and cited evidence."""

from .documents import DocumentChunk, load_document_bytes, load_document_path
from .hybrid import (
    Bm25Retriever,
    DenseRetriever,
    HybridRetriever,
    LexicalBaseline,
    RerankedRetriever,
    reciprocal_rank_fusion,
)
from .retrieval import SearchHit, build_local_answer, search_documents

__all__ = [
    "Bm25Retriever",
    "DenseRetriever",
    "DocumentChunk",
    "HybridRetriever",
    "LexicalBaseline",
    "RerankedRetriever",
    "SearchHit",
    "build_local_answer",
    "load_document_bytes",
    "load_document_path",
    "reciprocal_rank_fusion",
    "search_documents",
]
