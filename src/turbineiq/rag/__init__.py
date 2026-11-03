"""Local technical-document ingestion, search, and cited evidence."""

from .documents import DocumentChunk, load_document_bytes, load_document_path
from .retrieval import SearchHit, build_local_answer, search_documents

__all__ = [
    "DocumentChunk",
    "SearchHit",
    "build_local_answer",
    "load_document_bytes",
    "load_document_path",
    "search_documents",
]
