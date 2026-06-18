"""Resume text extraction from PDF/DOCX (replaces pdfminer/python-docx of the
original; here we use pypdf + python-docx)."""
from __future__ import annotations

import io

from app.core.logging import get_logger

log = get_logger("parsing")


def extract_text(content: bytes, filename: str = "", mime_type: str = "") -> str:
    name = (filename or "").lower()
    is_pdf = name.endswith(".pdf") or "pdf" in (mime_type or "")
    is_docx = name.endswith((".docx", ".doc")) or "word" in (mime_type or "") or "officedocument" in (mime_type or "")
    try:
        if is_pdf:
            return _pdf(content)
        if is_docx:
            return _docx(content)
        return content.decode("utf-8", errors="ignore")
    except Exception as exc:
        log.warning("text_extraction_failed", error=str(exc), filename=filename)
        return ""


def _pdf(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _docx(content: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(content))
    return "\n".join(p.text for p in document.paragraphs).strip()


def is_supported(filename: str = "", mime_type: str = "") -> bool:
    name = (filename or "").lower()
    return (
        name.endswith((".pdf", ".docx", ".doc"))
        or "pdf" in (mime_type or "")
        or "word" in (mime_type or "")
        or "officedocument" in (mime_type or "")
    )
