from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from turbineiq.rag import build_local_answer, load_document_bytes, search_documents
from turbineiq.rag.documents import DocumentLoadError


def make_one_page_pdf(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=320, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    font_ref = writer._add_object(font)
    resources = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    page[NameObject("/Resources")] = resources
    stream = DecodedStreamObject()
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream.set_data(f"BT /F1 12 Tf 30 100 Td ({escaped}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_markdown_ingestion_keeps_section_citations() -> None:
    content = (
        b"# Cycle model\nCompressor work uses the temperature rise.\n\n"
        b"## Limits\nNo OEM limits are included."
    )

    chunks = load_document_bytes("notes.md", content, chunk_size=120, overlap=20)

    assert {chunk.section for chunk in chunks} == {"Cycle model", "Limits"}
    assert chunks[0].citation == '[notes.md, section "Cycle model"]'


def test_text_ingestion_and_retrieval_return_relevant_source() -> None:
    chunks = load_document_bytes(
        "thermo.txt",
        b"The compressor raises pressure and temperature. "
        b"The turbine expands hot gas to produce work.",
    )

    hits = search_documents("compressor raises temperature", chunks)
    answer = build_local_answer("compressor temperature", hits)

    assert hits
    assert hits[0].chunk.source == "thermo.txt"
    assert "[thermo.txt]" in answer
    assert "no cloud model used" in answer


def test_pdf_ingestion_preserves_one_based_page_citation() -> None:
    chunks = load_document_bytes(
        "cycle.pdf", make_one_page_pdf("Turbine exhaust pressure equals ambient pressure.")
    )

    assert len(chunks) == 1
    assert "ambient pressure" in chunks[0].text
    assert chunks[0].citation == "[cycle.pdf, p. 1]"


def test_no_supporting_match_refuses_to_invent_an_answer() -> None:
    chunks = load_document_bytes("note.txt", b"Compressor work depends on the temperature rise.")

    hits = search_documents("hydrogen emissions controls", chunks)

    assert hits == []
    assert "could not find a supporting passage" in build_local_answer("unknown", hits)


@pytest.mark.parametrize(
    ("filename", "content"),
    [("manual.docx", b"content"), ("empty.txt", b""), ("bad.txt", b"\xff")],
)
def test_unreadable_or_unsupported_documents_are_rejected(filename: str, content: bytes) -> None:
    with pytest.raises(DocumentLoadError):
        load_document_bytes(filename, content)


@pytest.mark.parametrize(("chunk_size", "overlap"), [(99, 0), (100, 100), (100, -1)])
def test_bad_chunk_settings_are_rejected(chunk_size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        load_document_bytes("note.txt", b"small text", chunk_size=chunk_size, overlap=overlap)


def test_search_rejects_bad_top_k() -> None:
    chunks = load_document_bytes("note.txt", b"Compressor work depends on the temperature rise.")

    with pytest.raises(ValueError, match="top_k"):
        search_documents("compressor", chunks, top_k=0)
