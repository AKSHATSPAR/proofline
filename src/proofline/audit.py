from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

import pymupdf

from proofline.store import Store
from proofline.text import locate_evidence_rects, verify_evidence


def grounding_audit(store: Store) -> dict:
    """Measure deterministic page and word-level grounding without calling an LLM."""

    facts = store.facts()
    page_grounded = 0
    source_available = 0
    word_anchored = 0
    unanchored_fact_ids: list[str] = []

    with ExitStack() as stack:
        open_documents: dict[str, pymupdf.Document] = {}
        for fact in facts:
            page_text = store.page_text(fact.document_id, fact.page_number)
            valid, _ = verify_evidence(fact.evidence_quote, page_text or "")
            page_grounded += int(valid)

            document = store.document(fact.document_id)
            source_path = (
                Path(document["source_path"]) if document and document.get("source_path") else None
            )
            if source_path is None or not source_path.is_file():
                continue

            pdf = open_documents.get(fact.document_id)
            if pdf is None:
                try:
                    pdf = stack.enter_context(pymupdf.open(source_path))
                except (FileNotFoundError, RuntimeError):
                    continue
                open_documents[fact.document_id] = pdf
            if fact.page_number < 1 or fact.page_number > pdf.page_count:
                continue

            source_available += 1
            if locate_evidence_rects(pdf[fact.page_number - 1], fact.evidence_quote):
                word_anchored += 1
            else:
                unanchored_fact_ids.append(fact.id)

    accepted_facts = len(facts)
    return {
        "accepted_facts": accepted_facts,
        "page_grounded": page_grounded,
        "page_grounding_rate": page_grounded / accepted_facts if accepted_facts else 1.0,
        "source_available": source_available,
        "word_anchored": word_anchored,
        "word_anchor_rate": word_anchored / source_available if source_available else None,
        "unanchored_fact_ids": unanchored_fact_ids,
    }
