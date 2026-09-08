import pymupdf

from proofline.schemas import Page
from proofline.text import build_chunks, evidence_context, locate_evidence_rects, verify_evidence


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
