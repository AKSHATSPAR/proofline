from pathlib import Path

import pymupdf

from proofline.pipeline import KnowledgeLayer
from proofline.schemas import FactBatch, FactCandidate
from proofline.store import Store


class FakeExtractor:
    provider = "fake"
    model = "fake"

    def extract(self, document_name: str, chunk_text: str) -> FactBatch:
        return FactBatch(
            facts=[
                FactCandidate(
                    subject="Delhivery",
                    predicate="revenue from customers",
                    object_text="INR 8,142 crore",
                    value_type="number",
                    value_number=8142,
                    unit="INR crore",
                    normalized_value=81_420,
                    normalized_unit="INR million",
                    period_start="2023-04-01",
                    period_end="2024-03-31",
                    as_of_date=None,
                    scope=["consolidated"],
                    modality="actual",
                    comparison_key="delhivery|revenue from customers",
                    evidence_quote="Revenue from customers was INR 8,142 crore in FY24.",
                    page_number=1,
                    confidence=0.98,
                    extraction_note=None,
                )
            ]
        )


def make_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Revenue from customers was INR 8,142 crore in FY24.",
    )
    document.save(path)
    document.close()


def test_ingestion_is_grounded_and_incremental(tmp_path: Path) -> None:
    pdf_path = tmp_path / "annual-report.pdf"
    make_pdf(pdf_path)
    store = Store(tmp_path / "proofline.db")
    layer = KnowledgeLayer(store, FakeExtractor())

    first = layer.ingest_pdf(pdf_path)
    second = layer.ingest_pdf(pdf_path)

    assert first.facts_added == 1
    assert first.facts_rejected == 0
    assert second.skipped is True
    facts = store.facts()
    assert len(facts) == 1
    assert facts[0].evidence_status == "exact"
    assert facts[0].normalized_value == 81_420
    assert facts[0].extraction_method == "fake:fake"
