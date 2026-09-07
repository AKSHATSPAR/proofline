from proofline.relations import candidate_pairs
from proofline.schemas import StoredFact


def fact(identifier: str, document: str, key: str, predicate: str) -> StoredFact:
    return StoredFact(
        id=identifier,
        document_id=document,
        document_name=f"{document}.pdf",
        chunk_index=0,
        subject="Delhivery",
        predicate=predicate,
        object_text="8,142 crore",
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
        comparison_key=key,
        evidence_quote="Revenue from customers was 8,142 crore in FY24.",
        page_number=13,
        confidence=0.98,
        extraction_note=None,
        evidence_status="exact",
        extraction_method="test",
    )


def test_candidate_pairs_are_cross_document_and_semantically_blocked() -> None:
    facts = [
        fact("a", "doc-1", "delhivery|revenue from customers", "revenue from customers"),
        fact("b", "doc-2", "delhivery|customer revenue", "revenue from customers"),
        fact("c", "doc-2", "delhivery|active customers", "active customers"),
        fact("d", "doc-1", "delhivery|revenue from customers", "revenue from customers"),
    ]

    pairs = candidate_pairs(facts)

    assert ("a", "b") in pairs
    assert ("a", "d") not in pairs
    assert ("a", "c") not in pairs


def test_candidate_pairs_normalize_common_financial_paraphrases() -> None:
    facts = [
        fact("a", "doc-1", "delhivery|turnover", "turnover"),
        fact("b", "doc-2", "delhivery limited|revenue", "revenue from operations"),
        fact("c", "doc-3", "delhivery|employee headcount", "number of employees"),
    ]

    pairs = candidate_pairs(facts)

    assert ("a", "b") in pairs
    assert ("a", "c") not in pairs


def test_candidate_pairs_normalize_entity_suffixes_and_metric_phrases() -> None:
    left = fact("a", "doc-1", "india|gross domestic product growth", "economic growth")
    right = fact("b", "doc-2", "india limited|gdp growth", "real GDP growth")
    left = left.model_copy(update={"subject": "India"})
    right = right.model_copy(update={"subject": "India Limited"})

    assert candidate_pairs([left, right]) == [("a", "b")]
