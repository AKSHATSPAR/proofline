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


class FailingExtractor(FakeExtractor):
    def extract(self, document_name: str, chunk_text: str) -> FactBatch:
        raise RuntimeError("temporary provider failure")


class UnsupportedFactExtractor(FakeExtractor):
    def extract(self, document_name: str, chunk_text: str) -> FactBatch:
        batch = super().extract(document_name, chunk_text)
        fact = batch.facts[0].model_copy(
            update={
                "value_number": 9000,
                "normalized_value": 90_000,
                "period_start": "2024-04-01",
                "period_end": "2025-03-31",
            }
        )
        return FactBatch(facts=[fact])


class NoCallExtractor(FakeExtractor):
    def extract(self, document_name: str, chunk_text: str) -> FactBatch:
        raise AssertionError("A blank page must not be sent for extraction")


class EmptyExtractor(FakeExtractor):
    def extract(self, document_name: str, chunk_text: str) -> FactBatch:
        return FactBatch(facts=[])


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


def test_fully_failed_document_can_be_retried(tmp_path: Path) -> None:
    pdf_path = tmp_path / "annual-report.pdf"
    make_pdf(pdf_path)
    store = Store(tmp_path / "proofline.db")

    failed = KnowledgeLayer(store, FailingExtractor()).ingest_pdf(pdf_path)
    retried = KnowledgeLayer(store, FakeExtractor()).ingest_pdf(pdf_path)

    assert failed.status == "failed"
    assert failed.chunks_failed == 1
    assert retried.status == "ready"
    assert retried.skipped is False
    assert retried.facts_added == 1
    assert store.summary()["failures"] == 0


def test_ingestion_rejects_structured_meaning_not_supported_by_quote(tmp_path: Path) -> None:
    pdf_path = tmp_path / "annual-report.pdf"
    make_pdf(pdf_path)
    store = Store(tmp_path / "proofline.db")

    result = KnowledgeLayer(store, UnsupportedFactExtractor()).ingest_pdf(pdf_path)

    assert result.status == "rejected"
    assert result.facts_added == 0
    assert result.facts_rejected == 1
    assert store.facts() == []
    failure = store.failures()[0]
    assert failure["stage"] == "fact_validation"
    assert {issue["code"] for issue in failure["details"]["issues"]} >= {
        "number_not_in_evidence",
        "period_not_in_evidence",
    }


def test_blank_pdf_page_is_reported_as_unreadable(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scan.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(pdf_path)
    document.close()
    store = Store(tmp_path / "proofline.db")

    result = KnowledgeLayer(store, NoCallExtractor()).ingest_pdf(pdf_path)

    assert result.status == "failed"
    assert result.pages_unreadable == 1
    failure = store.failures()[0]
    assert failure["stage"] == "page_extraction"
    assert failure["page_number"] == 1


def test_empty_extraction_is_visible_and_not_marked_ready(tmp_path: Path) -> None:
    pdf_path = tmp_path / "annual-report.pdf"
    make_pdf(pdf_path)
    store = Store(tmp_path / "proofline.db")

    result = KnowledgeLayer(store, EmptyExtractor()).ingest_pdf(pdf_path)

    assert result.status == "empty"
    assert result.chunks_empty == 1
    assert store.failures()[0]["stage"] == "empty_extraction"
