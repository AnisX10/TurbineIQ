"""Read local TXT, Markdown, and PDF files into citation-bearing chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".pdf"}
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    source: str
    page_number: int | None
    section: str | None
    chunk_index: int

    @property
    def citation(self) -> str:
        if self.page_number is not None:
            return f"[{self.source}, p. {self.page_number}]"
        if self.section:
            return f'[{self.source}, section "{self.section}"]'
        return f"[{self.source}]"


class DocumentLoadError(ValueError):
    """Raised for unsupported or unreadable local technical documents."""


def _validate_chunking(chunk_size: int, overlap: int) -> None:
    if not isinstance(chunk_size, int) or chunk_size < 100:
        raise ValueError("chunk_size must be an integer of at least 100 characters")
    if not isinstance(overlap, int) or overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be a non-negative integer smaller than chunk_size")


def _split_text(
    text: str,
    *,
    source: str,
    page_number: int | None,
    section: str | None,
    chunk_size: int,
    overlap: int,
) -> list[DocumentChunk]:
    normalized = re.sub(r"[ \t]+", " ", text).strip()
    if not normalized:
        return []

    chunks: list[DocumentChunk] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary
        excerpt = normalized[start:end].strip()
        if excerpt:
            chunks.append(
                DocumentChunk(
                    text=excerpt,
                    source=source,
                    page_number=page_number,
                    section=section,
                    chunk_index=len(chunks),
                )
            )
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _markdown_sections(text: str) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    current: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            body = "\n".join(current).strip()
            if body:
                sections.append((heading, body))
            heading = match.group(1).strip()
            current = []
        else:
            current.append(line)
    body = "\n".join(current).strip()
    if body:
        sections.append((heading, body))
    return sections


def load_document_bytes(
    filename: str,
    content: bytes,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """Parse a document from bytes without writing uploads to disk."""

    _validate_chunking(chunk_size, overlap)
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise DocumentLoadError(f"unsupported document type {suffix or '(no extension)'}")
    if not content:
        raise DocumentLoadError("document is empty")
    source = Path(filename).name

    if suffix == ".pdf":
        try:
            reader = PdfReader(BytesIO(content), strict=False)
            chunks: list[DocumentChunk] = []
            for page_number, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                chunks.extend(
                    _split_text(
                        page_text,
                        source=source,
                        page_number=page_number,
                        section=None,
                        chunk_size=chunk_size,
                        overlap=overlap,
                    )
                )
            if not chunks:
                raise DocumentLoadError("PDF contains no extractable text")
            return [
                DocumentChunk(
                    text=chunk.text,
                    source=chunk.source,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    chunk_index=index,
                )
                for index, chunk in enumerate(chunks)
            ]
        except DocumentLoadError:
            raise
        except Exception as exc:
            raise DocumentLoadError(f"could not read PDF {source}: {exc}") from exc

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentLoadError(f"{source} must be UTF-8 text") from exc

    if suffix in {".md", ".markdown"}:
        sections = _markdown_sections(text)
    else:
        sections = [(None, text)]

    chunks = []
    for section, section_text in sections:
        chunks.extend(
            _split_text(
                section_text,
                source=source,
                page_number=None,
                section=section,
                chunk_size=chunk_size,
                overlap=overlap,
            )
        )
    if not chunks:
        raise DocumentLoadError(f"{source} contains no extractable text")
    return [
        DocumentChunk(
            text=chunk.text,
            source=chunk.source,
            page_number=chunk.page_number,
            section=chunk.section,
            chunk_index=index,
        )
        for index, chunk in enumerate(chunks)
    ]


def load_document_path(
    path: str | Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """Read one supported local file and return its chunks."""

    file_path = Path(path)
    try:
        content = file_path.read_bytes()
    except OSError as exc:
        raise DocumentLoadError(f"could not read {file_path.name}: {exc}") from exc
    return load_document_bytes(
        file_path.name,
        content,
        chunk_size=chunk_size,
        overlap=overlap,
    )
