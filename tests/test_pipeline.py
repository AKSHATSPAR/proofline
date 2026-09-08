from pathlib import Path

import pymupdf

from proofline.pipeline import KnowledgeLayer
from proofline.schemas import (
    FactBatch,
    FactCandidate,
    IndexedRelationDecision,
    RelationDecision,
    RelationDecisionBatch,
    StoredFact,
    TextChunk,
)
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
                    evidence_quote=(
                        "Delhivery's consolidated revenue from customers was "
                        "INR 8,142 crore in FY24."
                    ),
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


class UnrelatedExtractor(FakeExtractor):
    def __init__(self) -> None:
        self.comparisons = 0

    def compare(self, left, right, left_context="", right_context="") -> RelationDecision:
        self.comparisons += 1
        return RelationDecision(
            relation_type="unrelated",
            confidence=0.95,
            explanation="The source context does not support treating these facts as related.",
            decisive_context=["insufficient overlap"],
        )


class BatchUnrelatedExtractor(UnrelatedExtractor):
    def __init__(self) -> None:
        super().__init__()
        self.batch_calls = 0

    def compare(self, left, right, left_context="", right_context="") -> RelationDecision:
        raise AssertionError("The production adapter should use the batch comparison path")

    def compare_many(self, pairs) -> RelationDecisionBatch:
        self.batch_calls += 1
        return RelationDecisionBatch(
            decisions=[
                IndexedRelationDecision(
                    pair_index=index,
                    relation_type="unrelated",
                    confidence=0.95,
                    explanation="The source context does not support a material relationship.",
                    decisive_context=["insufficient overlap"],
                )
                for index, _ in enumerate(pairs)
            ]
        )


class ResumeExtractor(FakeExtractor):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.failed_second = False

    def extract(self, document_name: str, chunk_text: str) -> FactBatch:
        self.calls.append(chunk_text)
        if chunk_text == "second" and not self.failed_second:
            self.failed_second = True
            raise RuntimeError("temporary second-chunk failure")
        if chunk_text == "first":
            return super().extract(document_name, chunk_text)
        fact = (
            super()
            .extract(document_name, chunk_text)
            .facts[0]
            .model_copy(
                update={
                    "predicate": "parcel volume",
                    "object_text": "100 million parcels",
                    "value_number": 100,
                    "unit": "million parcels",
                    "normalized_value": None,
                    "normalized_unit": None,
                    "comparison_key": "delhivery|parcel volume",
                    "evidence_quote": (
                        "Delhivery's consolidated parcel volume was 100 million parcels in FY24."
                    ),
                }
            )
        )
        return FactBatch(facts=[fact])


def make_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Delhivery's consolidated revenue from customers was INR 8,142 crore in FY24.",
    )
    document.save(path)
    document.close()


def make_two_fact_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Delhivery's consolidated revenue from customers was INR 8,142 crore in FY24.",
    )
    page.insert_text(
        (72, 96),
        "Delhivery's consolidated parcel volume was 100 million parcels in FY24.",
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


def test_partial_retry_preserves_completed_chunks(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "annual-report.pdf"
    make_two_fact_pdf(pdf_path)
    store = Store(tmp_path / "proofline.db")
    extractor = ResumeExtractor()
    monkeypatch.setattr(
        "proofline.pipeline.build_chunks",
        lambda pages: [
            TextChunk(index=0, pages=[1], text="first"),
            TextChunk(index=1, pages=[1], text="second"),
        ],
    )
    layer = KnowledgeLayer(store, extractor)

    first = layer.ingest_pdf(pdf_path)
    retried = layer.ingest_pdf(pdf_path)

    assert first.status == "partial"
    assert retried.status == "ready"
    assert extractor.calls == ["first", "second", "second"]
    assert len(store.facts()) == 2
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


def test_unrelated_relation_decision_is_not_repeated(tmp_path: Path) -> None:
    store = Store(tmp_path / "proofline.db")
    source_fact = FakeExtractor().extract("source.pdf", "text").facts[0]
    for suffix in ("a", "b"):
        document_id = f"doc-{suffix}"
        store.add_document(
            document_id,
            f"{suffix}.pdf",
            f"hash-{suffix}",
            [(1, source_fact.evidence_quote)],
        )
        store.set_document_status(document_id, "ready")
        store.add_fact(
            StoredFact(
                **source_fact.model_dump(),
                id=f"fact-{suffix}",
                document_id=document_id,
                document_name=f"{suffix}.pdf",
                chunk_index=0,
                evidence_status="exact",
                extraction_method="test",
            )
        )

    extractor = UnrelatedExtractor()
    layer = KnowledgeLayer(store, extractor)

    assert layer.discover_relations() == 0
    assert layer.discover_relations() == 0
    assert extractor.comparisons == 1
    assert store.checked_relation_pairs() == {("fact-a", "fact-b")}


def test_relation_candidates_are_classified_in_one_batch(tmp_path: Path) -> None:
    store = Store(tmp_path / "proofline.db")
    source_fact = FakeExtractor().extract("source.pdf", "text").facts[0]
    for suffix in ("a", "b", "c"):
        document_id = f"doc-{suffix}"
        store.add_document(
            document_id,
            f"{suffix}.pdf",
            f"hash-{suffix}",
            [(1, source_fact.evidence_quote)],
        )
        store.set_document_status(document_id, "ready")
        store.add_fact(
            StoredFact(
                **source_fact.model_dump(),
                id=f"fact-{suffix}",
                document_id=document_id,
                document_name=f"{suffix}.pdf",
                chunk_index=0,
                evidence_status="exact",
                extraction_method="test",
            )
        )

    extractor = BatchUnrelatedExtractor()

    assert KnowledgeLayer(store, extractor).discover_relations() == 0
    assert extractor.batch_calls == 1
    assert len(store.checked_relation_pairs()) == 3
