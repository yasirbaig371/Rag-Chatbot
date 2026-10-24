import hashlib
import io
import os
import re
import uuid
from typing import Any, BinaryIO, Dict, List, Tuple
import pypdf

from app.core.config import settings

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MAX_FILE_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024  # 10 MB


class PDFValidationError(Exception):
    """Raised when uploaded file fails format, MIME, or signature validation."""
    pass


class PDFSizeLimitError(Exception):
    """Raised when uploaded file exceeds the 10MB maximum size limit."""
    pass


class PDFEmptyError(Exception):
    """Raised when PDF contains no extractable text (e.g., scanned/image-only PDFs)."""
    pass


def sanitize_filename(filename: str) -> str:
    """Sanitizes user-provided filename for safe display."""
    base = re.split(r"[\\/]", filename)[-1]
    # Remove potentially dangerous characters
    cleaned = re.sub(r"[^\w\s.-]", "_", base).strip()
    return cleaned or "document.pdf"


def read_and_validate_pdf_stream(
    stream: BinaryIO,
    filename: str,
    content_type: str | None,
) -> Tuple[bytes, str]:
    """Reads PDF stream enforcing size limits, extension, MIME, magic bytes, and computing SHA-256."""
    # 1. Validate file extension
    if not filename.lower().endswith(".pdf"):
        raise PDFValidationError("Invalid file extension. Only .pdf files are accepted.")

    # 2. Validate declared MIME type
    if content_type != "application/pdf":
        raise PDFValidationError("Invalid MIME type. Only application/pdf is supported.")

    # 3. Stream bytes up to MAX_FILE_BYTES and compute SHA-256 hash
    hasher = hashlib.sha256()
    buffer = bytearray()
    chunk_size = 64 * 1024  # 64 KB read buffer

    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        buffer.extend(chunk)
        hasher.update(chunk)
        if len(buffer) > MAX_FILE_BYTES:
            raise PDFSizeLimitError(
                f"File size exceeds maximum allowed limit of {settings.MAX_UPLOAD_SIZE_MB}MB."
            )

    file_bytes = bytes(buffer)
    if not file_bytes:
        raise PDFValidationError("Uploaded file is empty.")

    # Require the PDF header at the beginning instead of trusting MIME metadata.
    if not file_bytes.startswith(b"%PDF-"):
        raise PDFValidationError("Invalid PDF file signature. The file is not a valid PDF document.")

    file_hash = hasher.hexdigest()
    return file_bytes, file_hash


def extract_text_by_page(file_bytes: bytes) -> List[Tuple[int, str]]:
    """Extracts text page-by-page using pypdf, checking for corruption, encryption, and empty text."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:
        raise PDFValidationError("The uploaded PDF is corrupted or unreadable.") from exc

    if reader.is_encrypted:
        raise PDFValidationError("Password-protected or encrypted PDFs are not supported.")

    page_count = len(reader.pages)
    if page_count == 0:
        raise PDFValidationError("The PDF document contains 0 pages.")

    pages_data: List[Tuple[int, str]] = []
    total_extracted_chars = 0

    for idx, page in enumerate(reader.pages):
        page_num = idx + 1
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:
            raise PDFValidationError("The uploaded PDF contains a page that cannot be read.") from exc

        # Normalize whitespace
        clean_text = " ".join(page_text.split())
        if clean_text:
            total_extracted_chars += len(clean_text)
        pages_data.append((page_num, clean_text))

    if total_extracted_chars == 0:
        raise PDFEmptyError(
            "The PDF has no extractable text; OCR is not supported."
        )

    return pages_data


def chunk_pages(
    pages_data: List[Tuple[int, str]],
    document_id: int,
    title: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> List[Dict[str, Any]]:
    """Splits extracted page text into chunks of 800 characters with 100 character overlap.

    Retains page metadata and generates stable chunk IDs (doc_{document_id}_chunk_{index}).
    """
    chunks: List[Dict[str, Any]] = []
    step = chunk_size - chunk_overlap
    global_chunk_idx = 0

    for page_num, text in pages_data:
        if not text:
            continue
        text_len = len(text)
        if text_len <= chunk_size:
            chunk_id = f"doc_{document_id}_chunk_{global_chunk_idx}"
            chunks.append({
                "id": chunk_id,
                "text": text,
                "metadata": {
                    "document_id": document_id,
                    "title": title,
                    "page": page_num,
                    "chunk_index": global_chunk_idx,
                    "chunk_id": chunk_id,
                },
            })
            global_chunk_idx += 1
        else:
            start = 0
            while start < text_len:
                end = min(start + chunk_size, text_len)
                chunk_slice = text[start:end]
                if chunk_slice:
                    chunk_id = f"doc_{document_id}_chunk_{global_chunk_idx}"
                    chunks.append({
                        "id": chunk_id,
                        "text": chunk_slice,
                        "metadata": {
                            "document_id": document_id,
                            "title": title,
                            "page": page_num,
                            "chunk_index": global_chunk_idx,
                            "chunk_id": chunk_id,
                        },
                    })
                    global_chunk_idx += 1
                if end >= text_len:
                    break
                start += step

    return chunks


def save_pdf_to_disk(file_bytes: bytes) -> Tuple[str, str]:
    """Saves PDF bytes to UPLOAD_DIR with a unique UUID filename."""
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    server_filename = f"{uuid.uuid4()}.pdf"
    file_path = os.path.join(settings.UPLOAD_DIR, server_filename)
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    return file_path, server_filename
