from proofline.schemas import Page
from proofline.text import build_chunks, verify_evidence


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
