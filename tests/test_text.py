import pymupdf

from proofline.schemas import Page
from proofline.text import (
    build_chunks,
    evidence_context,
    extract_pages,
    locate_evidence_rects,
    verify_evidence,
)


def test_chunks_keep_page_labels_and_bounds() -> None:
    pages = [
        Page(page_number=1, text="A" * 50),
        Page(page_number=2, text="B" * 50),
    ]

    chunks = build_chunks(pages, max_chars=80, overlap_chars=10)

    assert len(chunks) == 2
    assert chunks[0].pages == [1]
    assert "[[PDF_PAGE 1]]" in chunks[0].text
    assert chunks[1].pages == [2]


def test_default_chunk_size_keeps_large_documents_within_a_small_request_budget() -> None:
    pages = [Page(page_number=index, text="A" * 9_500) for index in range(1, 101)]

    chunks = build_chunks(pages)

    assert len(chunks) <= 20


def test_evidence_matching_is_whitespace_tolerant_but_not_fuzzy() -> None:
    page = "Revenue from customers\nwas INR 8,142 crore in FY24."

    assert verify_evidence("Revenue from customers was INR 8,142 crore", page) == (
        True,
        "exact",
    )
    assert verify_evidence("Revenue was about INR 8,142 crore", page) == (
        False,
        "not_found",
    )


def test_word_level_anchor_handles_normalized_footnote_glyphs() -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Although real gross domestic product (GDP)3 growth moderated to 6.5 per cent.",
    )

    rects = locate_evidence_rects(
        page,
        "Although real gross domestic product (GDP)³ growth moderated to 6.5 per cent.",
    )

    assert rects
    assert all(rect.width > 0 and rect.height > 0 for rect in rects)
    assert locate_evidence_rects(page, "This quote is not present on the page.") == []
    document.close()


def test_word_level_anchor_can_omit_a_trailing_footnote_marker() -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Although real gross domestic product (GDP)3 growth moderated to 6.5 per cent.",
    )

    rects = locate_evidence_rects(
        page,
        "Although real gross domestic product (GDP) growth moderated to 6.5 per cent.",
    )

    assert rects
    assert locate_evidence_rects(page, "growth moderated to 6 per cent") == []
    document.close()


def test_evidence_context_returns_a_bounded_window_around_the_quote() -> None:
    page = f"{'before ' * 100}Revenue was INR 8,142 crore in FY24.{' after' * 100}"

    context = evidence_context(page, "Revenue was INR 8,142 crore in FY24.", radius=30)

    assert context.startswith("... ")
    assert context.endswith(" ...")
    assert "Revenue was INR 8,142 crore in FY24." in context
    assert len(context) < len(page)


def test_table_layout_context_preserves_headers_without_becoming_evidence(tmp_path) -> None:
    path = tmp_path / "table.pdf"
    document = pymupdf.open()
    page = document.new_page(width=500, height=300)
    for y in (60, 100, 140):
        page.draw_line((50, y), (450, y))
    for x in (50, 250, 350, 450):
        page.draw_line((x, 60), (x, 140))
    page.insert_text((60, 85), "Metric")
    page.insert_text((260, 85), "Mar 23")
    page.insert_text((360, 85), "Mar 24")
    page.insert_text((60, 125), "Revenue")
    page.insert_text((275, 125), "100")
    page.insert_text((375, 125), "120")
    document.save(path)
    document.close()

    extracted = extract_pages(path)[0]

    assert "[[LAYOUT_TABLE_CONTEXT - INTERPRETATION ONLY]]" in extracted.analysis_text
    assert "Metric | Mar 23 | Mar 24" in extracted.analysis_text
    assert "Revenue | 100 | 120" in extracted.analysis_text
    assert "[[LAYOUT_TABLE_CONTEXT" not in extracted.text
    assert verify_evidence("Revenue | 100 | 120", extracted.text) == (False, "not_found")
    assert "Metric | Mar 23 | Mar 24" in build_chunks([extracted])[0].text
