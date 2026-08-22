"""PDF text extraction, kept behind a seam.

`pypdf` is pure Python and small — chosen over pdfplumber (which pulls Pillow)
and far over the spec's sentence-transformers stack, which would have brought
PyTorch into a slim image for no gain that FTS5 does not already provide.

The extractor is injectable so the test suite stays offline and dependency
free: tests pass their own callable and never touch a real PDF.
"""
from __future__ import annotations

from typing import Callable

# (pdf_bytes) -> list of page texts, in reading order.
Extractor = Callable[[bytes], list[str]]


def pypdf_extract(data: bytes) -> list[str]:
    """Per-page text via pypdf. Empty list if the dependency is absent.

    Scanned decks that carry no text layer come back as empty pages; OCR is
    out of scope, and `pages_with_text` in the ingest result makes such a file
    visible rather than silently indexed as nothing.
    """
    try:
        import io

        from pypdf import PdfReader
    except ImportError:
        return []
    try:
        reader = PdfReader(io.BytesIO(data))
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception:
        return []


def normalize(text: str) -> str:
    """Collapse the whitespace PDF extraction scatters through a page."""
    return " ".join((text or "").split())
