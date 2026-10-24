from io import BytesIO
import hashlib

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services import pdf_service


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class FakeReader:
    def __init__(self, pages: list[FakePage], encrypted: bool = False) -> None:
        self.pages = pages
        self.is_encrypted = encrypted


def _make_text_pdf() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_reference}
            )
        }
    )
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 72 720 Td (Extractable sample text) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_read_and_validate_pdf_stream_checks_signature_and_hash() -> None:
    content = b"%PDF-1.7 test document"

    file_bytes, file_hash = pdf_service.read_and_validate_pdf_stream(
        BytesIO(content),
        "sample.pdf",
        "application/pdf",
    )

    assert file_bytes == content
    assert file_hash == hashlib.sha256(content).hexdigest()


def test_extract_text_from_valid_pdf() -> None:
    pages = pdf_service.extract_text_by_page(_make_text_pdf())

    assert pages == [(1, "Extractable sample text")]


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        ("sample.txt", "application/pdf", b"%PDF-1.7"),
        ("sample.pdf", "text/plain", b"%PDF-1.7"),
        ("sample.pdf", "application/pdf", b"not a pdf"),
    ],
)
def test_read_and_validate_pdf_stream_rejects_invalid_metadata_or_signature(
    filename: str,
    content_type: str,
    content: bytes,
) -> None:
    with pytest.raises(pdf_service.PDFValidationError):
        pdf_service.read_and_validate_pdf_stream(
            BytesIO(content),
            filename,
            content_type,
        )


def test_read_and_validate_pdf_stream_enforces_limit_while_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pdf_service, "MAX_FILE_BYTES", 8)

    with pytest.raises(pdf_service.PDFSizeLimitError):
        pdf_service.read_and_validate_pdf_stream(
            BytesIO(b"%PDF-1234"),
            "sample.pdf",
            "application/pdf",
        )


def test_extract_text_rejects_corrupted_encrypted_zero_page_and_textless_pdfs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pdf_service.pypdf,
        "PdfReader",
        lambda _: (_ for _ in ()).throw(RuntimeError("sensitive internal detail")),
    )
    with pytest.raises(pdf_service.PDFValidationError) as corrupted:
        pdf_service.extract_text_by_page(b"%PDF-invalid")
    assert "sensitive internal detail" not in str(corrupted.value)

    monkeypatch.setattr(
        pdf_service.pypdf,
        "PdfReader",
        lambda _: FakeReader([], encrypted=True),
    )
    with pytest.raises(pdf_service.PDFValidationError, match="encrypted"):
        pdf_service.extract_text_by_page(b"%PDF-encrypted")

    monkeypatch.setattr(
        pdf_service.pypdf,
        "PdfReader",
        lambda _: FakeReader([]),
    )
    with pytest.raises(pdf_service.PDFValidationError, match="0 pages"):
        pdf_service.extract_text_by_page(b"%PDF-empty")

    monkeypatch.setattr(
        pdf_service.pypdf,
        "PdfReader",
        lambda _: FakeReader([FakePage("  \n  ")]),
    )
    with pytest.raises(pdf_service.PDFEmptyError, match="OCR is not supported"):
        pdf_service.extract_text_by_page(b"%PDF-image-only")


def test_chunk_pages_preserves_page_metadata_and_exact_overlap() -> None:
    text = "a" * 1600

    chunks = pdf_service.chunk_pages(
        [(1, text), (2, ""), (3, "A later page.")],
        document_id=42,
        title="Reference",
    )

    assert len(chunks) == 4
    first, second, third, fourth = chunks
    assert len(first["text"]) == 800
    assert first["text"][700:] == second["text"][:100]
    assert [chunk["id"] for chunk in chunks] == [
        "doc_42_chunk_0",
        "doc_42_chunk_1",
        "doc_42_chunk_2",
        "doc_42_chunk_3",
    ]
    assert first["metadata"] == {
        "document_id": 42,
        "title": "Reference",
        "page": 1,
        "chunk_index": 0,
        "chunk_id": "doc_42_chunk_0",
    }
    assert third["metadata"]["page"] == 1
    assert fourth["metadata"]["page"] == 3
    assert max(len(chunk["text"]) for chunk in chunks) <= 800


def test_sanitize_filename_handles_windows_paths_and_unsafe_characters() -> None:
    assert pdf_service.sanitize_filename(r"C:\private\my report?.pdf") == "my report_.pdf"
