"""Resume text + hyperlink extraction from PDF/DOCX.

Beyond the visible text, we pull the document's *hyperlink annotations*
(``mailto:``/``tel:``/``http``). Resumes built with LaTeX/icon fonts (moderncv,
FontAwesome, …) render the contact line as icon glyphs, so ``extract_text``
returns garbage like ``/envel<glyph>peprachipant05@gmail.com`` — the visible
email is corrupted but the real address lives in the ``mailto:`` link. The link
data is authoritative and is both appended to the text (for the LLM) and
returned separately (for deterministic reconciliation in the intake agent).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from app.core.logging import get_logger

log = get_logger("parsing")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Private-use-area + miscellaneous-symbol glyphs left behind by icon fonts.
# They sit next to contact details and corrupt them, so strip them out.
_GLYPH_NOISE_RE = re.compile(
    "["
    "-"   # private use area (FontAwesome & friends)
    "←-⇿"   # arrows
    "⌀-⏿"   # misc technical (incl. U+2322 envelope-ish glyph)
    "①-⓿"   # enclosed alphanumerics
    "☀-➿"   # misc symbols & dingbats
    "♀♂"    # gender symbols
    "]"
)
_SOCIAL_HOSTS = ("linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com")


@dataclass
class DetectedLinks:
    """Contact details recovered from a document's hyperlink annotations."""

    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    portfolio_url: str | None = None
    urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "phone": self.phone,
            "linkedin_url": self.linkedin_url,
            "portfolio_url": self.portfolio_url,
            "urls": list(self.urls),
        }

    def as_block(self) -> str:
        """A human/LLM-readable summary appended to the resume text."""
        lines = []
        if self.email:
            lines.append(f"Email: {self.email}")
        if self.phone:
            lines.append(f"Phone: {self.phone}")
        if self.linkedin_url:
            lines.append(f"LinkedIn: {self.linkedin_url}")
        if self.portfolio_url:
            lines.append(f"Portfolio/GitHub: {self.portfolio_url}")
        extra = [u for u in self.urls if u not in {self.linkedin_url, self.portfolio_url}]
        if extra:
            lines.append("Other links: " + ", ".join(extra[:10]))
        if not lines:
            return ""
        return (
            "VERIFIED CONTACT LINKS (extracted directly from the document's hyperlinks — "
            "trust these over the body text for email, phone and URLs):\n" + "\n".join(lines)
        )


def clean_email(value: str | None) -> str | None:
    """Pull the first well-formed email address out of `value`, lowercased."""
    if not value:
        return None
    match = _EMAIL_RE.search(value)
    return match.group(0).lower() if match else None


def extract_document(content: bytes, filename: str = "", mime_type: str = "") -> tuple[str, DetectedLinks]:
    """Return (cleaned_text, detected_links). The links block is appended to the text."""
    name = (filename or "").lower()
    is_pdf = name.endswith(".pdf") or "pdf" in (mime_type or "")
    is_docx = name.endswith((".docx", ".doc")) or "word" in (mime_type or "") or "officedocument" in (mime_type or "")
    try:
        if is_pdf:
            text, links = _pdf(content)
        elif is_docx:
            text, links = _docx(content)
        else:
            text, links = content.decode("utf-8", errors="ignore"), DetectedLinks()
    except Exception as exc:
        log.warning("text_extraction_failed", error=str(exc), filename=filename)
        return "", DetectedLinks()

    text = _clean(text)
    block = links.as_block()
    if block:
        text = f"{text}\n\n{block}"
    return text, links


def extract_text(content: bytes, filename: str = "", mime_type: str = "") -> str:
    return extract_document(content, filename, mime_type)[0]


def _pdf(content: bytes) -> tuple[str, DetectedLinks]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()

    uris: list[str] = []
    for page in reader.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        try:
            annots = annots.get_object()
        except Exception:
            pass
        for ref in annots:
            try:
                obj = ref.get_object()
                action = obj.get("/A")
                uri = action.get("/URI") if action else None
            except Exception:
                continue
            if uri:
                uris.append(str(uri))
    return text, _links_from_uris(uris)


def _docx(content: bytes) -> tuple[str, DetectedLinks]:
    import docx

    document = docx.Document(io.BytesIO(content))
    text = "\n".join(p.text for p in document.paragraphs).strip()
    uris = [
        str(rel.target_ref)
        for rel in document.part.rels.values()
        if "hyperlink" in rel.reltype and getattr(rel, "target_ref", None)
    ]
    return text, _links_from_uris(uris)


def _links_from_uris(uris: list[str]) -> DetectedLinks:
    links = DetectedLinks()
    for raw in uris:
        uri = (raw or "").strip()
        low = uri.lower()
        if low.startswith("mailto:"):
            addr = clean_email(uri[len("mailto:"):])
            if addr and links.email is None:
                links.email = addr
        elif low.startswith("tel:"):
            if links.phone is None:
                links.phone = uri[len("tel:"):].strip()
        elif low.startswith(("http://", "https://")):
            if uri not in links.urls:
                links.urls.append(uri)
            if "linkedin.com" in low:
                if links.linkedin_url is None:
                    links.linkedin_url = uri
            elif links.portfolio_url is None and _is_profile_url(low):
                links.portfolio_url = uri
    return links


def _is_profile_url(low: str) -> bool:
    """A personal profile / portfolio page rather than a deep project link."""
    if any(host in low for host in _SOCIAL_HOSTS):
        return False
    if "github.com/" in low:
        # github.com/<user> is a profile; github.com/<user>/<repo> is a project.
        path = low.split("github.com/", 1)[1].strip("/")
        return bool(path) and "/" not in path
    return True  # any other non-social site — treat as a portfolio/personal site


def _clean(text: str) -> str:
    if not text:
        return ""
    text = _GLYPH_NOISE_RE.sub(" ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def is_supported(filename: str = "", mime_type: str = "") -> bool:
    name = (filename or "").lower()
    return (
        name.endswith((".pdf", ".docx", ".doc"))
        or "pdf" in (mime_type or "")
        or "word" in (mime_type or "")
        or "officedocument" in (mime_type or "")
    )
