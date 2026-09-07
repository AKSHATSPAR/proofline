from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import pymupdf

from proofline.schemas import Page, TextChunk

_WHITESPACE = re.compile(r"\s+")


def normalize_whitespace(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def extract_pages(pdf_path: Path) -> list[Page]:
    """Extract text one page at a time so every downstream claim keeps provenance."""

    pages: list[Page] = []
    with pymupdf.open(pdf_path) as document:
        for index, pdf_page in enumerate(document):
            text = pdf_page.get_text("text", sort=True)
            pages.append(Page(page_number=index + 1, text=text))
    return pages


def _split_long_page(page: Page, max_chars: int, overlap_chars: int) -> Iterable[str]:
    text = page.text.strip()
    if len(text) <= max_chars:
        yield text
        return

    start = 0
    while start < len(text):
        stop = min(start + max_chars, len(text))
        if stop < len(text):
            newline = text.rfind("\n", start + max_chars // 2, stop)
            if newline > start:
                stop = newline
        yield text[start:stop]
        if stop == len(text):
            break
        start = max(stop - overlap_chars, start + 1)


def build_chunks(
    pages: list[Page], max_chars: int = 14_000, overlap_chars: int = 800
) -> list[TextChunk]:
    """Create page-labelled chunks without allowing provenance to drift."""

    chunks: list[TextChunk] = []
    pending: list[str] = []
    pending_pages: list[int] = []
    pending_size = 0

    def flush() -> None:
        nonlocal pending, pending_pages, pending_size
        if pending:
            chunks.append(
                TextChunk(index=len(chunks), pages=pending_pages, text="\n\n".join(pending))
            )
        pending = []
        pending_pages = []
        pending_size = 0

    for page in pages:
        for fragment in _split_long_page(page, max_chars, overlap_chars):
            labelled = f"[[PDF_PAGE {page.page_number}]]\n{fragment}"
            if pending and pending_size + len(labelled) > max_chars:
                flush()
            pending.append(labelled)
            pending_pages.append(page.page_number)
            pending_size += len(labelled)
            if len(labelled) >= max_chars:
                flush()
    flush()
    return chunks


def verify_evidence(quote: str, page_text: str) -> tuple[bool, str]:
    """Anchor model evidence to extracted text using whitespace-tolerant exact matching."""

    normalized_quote = normalize_whitespace(quote)
    normalized_page = normalize_whitespace(page_text)
    if len(normalized_quote) < 12:
        return False, "too_short"
    if normalized_quote in normalized_page:
        return True, "exact"
    return False, "not_found"
