from __future__ import annotations

import contextlib
import io
import re
from collections.abc import Iterable
from pathlib import Path

import pymupdf

from proofline.schemas import Page, TextChunk

_WHITESPACE = re.compile(r"\s+")
_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_MAX_TABLE_CONTEXT_CHARS = 12_000


def normalize_whitespace(value: str) -> str:
    # PDF engines disagree on whether footnote glyphs are emitted as plain or
    # superscript digits. Treat those glyph variants as the same source text.
    return _WHITESPACE.sub(" ", value.translate(_SUPERSCRIPT_DIGITS)).strip()


def _layout_table_context(pdf_page: pymupdf.Page) -> str:
    """Return a bounded, deterministic table view for interpretation only.

    The ordinary page text remains the sole source accepted by the evidence gate.
    This view only helps the extractor associate row values with visible headers.
    """

    rendered_tables: list[str] = []
    try:
        # PyMuPDF prints an optional layout-package notice directly to the console.
        # The built-in detector is intentional here, so keep command output focused
        # on document progress and actual failures.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            tables = pdf_page.find_tables().tables
    except (AttributeError, RuntimeError, ValueError):
        return ""

    for table_index, table in enumerate(tables, start=1):
        rows = table.extract()
        if table.row_count < 2 or table.col_count < 2 or not rows:
            continue
        rendered_rows = []
        for row in rows:
            cells = [normalize_whitespace(cell or "") for cell in row]
            if any(cells):
                rendered_rows.append(" | ".join(cells))
        if len(rendered_rows) < 2:
            continue
        rendered_tables.append(f"[[TABLE {table_index}]]\n" + "\n".join(rendered_rows))

    if not rendered_tables:
        return ""
    return "\n\n".join(rendered_tables)[:_MAX_TABLE_CONTEXT_CHARS]


def extract_pages(pdf_path: Path) -> list[Page]:
    """Extract text one page at a time so every downstream claim keeps provenance."""

    pages: list[Page] = []
    with pymupdf.open(pdf_path) as document:
        for index, pdf_page in enumerate(document):
            # Preserve the PDF content stream's reading order. Coordinate sorting often
            # interleaves rows from adjacent columns, breaking otherwise verbatim evidence.
            text = pdf_page.get_text("text", sort=False)
            table_context = _layout_table_context(pdf_page)
            analysis_text = text
            if table_context:
                analysis_text = (
                    f"{text.rstrip()}\n\n"
                    "[[LAYOUT_TABLE_CONTEXT - INTERPRETATION ONLY]]\n"
                    f"{table_context}\n"
                    "[[END_LAYOUT_TABLE_CONTEXT]]"
                )
            pages.append(
                Page(
                    page_number=index + 1,
                    text=text,
                    analysis_text=analysis_text,
                )
            )
    return pages


def _split_long_page(page: Page, max_chars: int, overlap_chars: int) -> Iterable[str]:
    text = (page.analysis_text or page.text).strip()
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
    pages: list[Page], max_chars: int = 60_000, overlap_chars: int = 1_500
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
            if not fragment.strip():
                continue
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


def document_identity_context(pages: list[Page], max_chars: int = 4_000) -> str:
    """Collect a small source-backed identity window from the document opening."""

    context = "\n".join(page.text for page in pages[:3] if normalize_whitespace(page.text))
    return context[:max_chars]


def verify_evidence(quote: str, page_text: str) -> tuple[bool, str]:
    """Anchor model evidence to extracted text using whitespace-tolerant exact matching."""

    normalized_quote = normalize_whitespace(quote)
    normalized_page = normalize_whitespace(page_text)
    if len(normalized_quote) < 12:
        return False, "too_short"
    if normalized_quote in normalized_page:
        return True, "exact"
    return False, "not_found"


def evidence_context(page_text: str, quote: str, radius: int = 500) -> str:
    """Return a bounded source window around a verified quote."""

    normalized_page = normalize_whitespace(page_text)
    normalized_quote = normalize_whitespace(quote)
    quote_start = normalized_page.find(normalized_quote)
    if quote_start < 0:
        return ""

    start = max(0, quote_start - radius)
    end = min(len(normalized_page), quote_start + len(normalized_quote) + radius)
    if start:
        next_space = normalized_page.find(" ", start)
        start = next_space + 1 if next_space >= 0 else start
    if end < len(normalized_page):
        previous_space = normalized_page.rfind(" ", start, end)
        end = previous_space if previous_space >= 0 else end

    context = normalized_page[start:end]
    if start:
        context = f"... {context}"
    if end < len(normalized_page):
        context = f"{context} ..."
    return context


def locate_evidence_rects(page: pymupdf.Page, quote: str) -> list[pymupdf.Rect]:
    """Locate a verified quote on its PDF page for visual, word-level provenance.

    PyMuPDF's native search handles wrapped and hyphenated text. The word-sequence fallback covers
    glyph variants that the evidence gate intentionally normalizes, such as superscript footnotes.
    """

    quads = page.search_for(quote, quads=True)
    if quads:
        return [quad.rect for quad in quads]

    quote_tokens = [token.casefold() for token in normalize_whitespace(quote).split()]
    if not quote_tokens:
        return []

    words = page.get_text("words", sort=False)
    word_tokens = [normalize_whitespace(word[4]).casefold() for word in words]

    def token_matches(source: str, expected: str) -> bool:
        if source == expected:
            return True
        # Some PDFs expose a superscript footnote as an ordinary trailing digit.
        # Only ignore it when the quoted token itself does not end in a digit, so
        # values and years can never be shortened into a visual match.
        return bool(
            expected and not expected[-1].isdigit() and source.rstrip("0123456789") == expected
        )

    match_start = next(
        (
            index
            for index in range(len(word_tokens) - len(quote_tokens) + 1)
            if all(
                token_matches(source, expected)
                for source, expected in zip(
                    word_tokens[index : index + len(quote_tokens)], quote_tokens, strict=True
                )
            )
        ),
        None,
    )
    if match_start is None:
        return []

    matched_words = words[match_start : match_start + len(quote_tokens)]
    rects: list[pymupdf.Rect] = []
    current_line: tuple[int, int] | None = None
    current_rect: pymupdf.Rect | None = None
    for word in matched_words:
        line = (word[5], word[6])
        word_rect = pymupdf.Rect(word[:4])
        if line != current_line:
            if current_rect is not None:
                rects.append(current_rect)
            current_line = line
            current_rect = word_rect
        elif current_rect is not None:
            current_rect.include_rect(word_rect)
    if current_rect is not None:
        rects.append(current_rect)
    return rects
