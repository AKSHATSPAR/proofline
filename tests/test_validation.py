from proofline.schemas import FactCandidate, RelationDecision, StoredFact
from proofline.validation import validate_fact_semantics, validate_relation_semantics


def candidate(**updates) -> FactCandidate:
    payload = {
        "subject": "Delhivery",
        "predicate": "revenue from customers",
        "object_text": "INR 8,142 crore",
        "value_type": "number",
        "value_number": 8142,
        "unit": "INR crore",
        "normalized_value": 81_420,
        "normalized_unit": "INR million",
        "period_start": "2023-04-01",
        "period_end": "2024-03-31",
        "as_of_date": None,
        "scope": ["consolidated"],
        "modality": "actual",
        "comparison_key": "delhivery|revenue from customers",
        "evidence_quote": (
            "Delhivery's consolidated revenue from customers was INR 8,142 crore in FY24."
        ),
        "page_number": 1,
        "confidence": 0.98,
        "extraction_note": None,
    }
    payload.update(updates)
    return FactCandidate.model_validate(payload)


def stored(identifier: str, value: float, period_end: str = "2024-03-31") -> StoredFact:
    return StoredFact(
        **candidate(
            value_number=value,
            object_text=str(value),
            normalized_value=value,
            unit="percent",
            normalized_unit="percent",
            evidence_quote=f"Revenue was {value}% in FY24.",
            period_end=period_end,
        ).model_dump(),
        id=identifier,
        document_id=f"doc-{identifier}",
        document_name=f"{identifier}.pdf",
        chunk_index=0,
        evidence_status="exact",
        extraction_method="test",
    )


def test_fact_semantics_accept_supported_number_period_unit_and_conversion() -> None:
    assert validate_fact_semantics(candidate()) == []


def test_fact_semantics_reject_structured_fields_not_supported_by_quote() -> None:
    issues = validate_fact_semantics(
        candidate(
            value_number=9000,
            period_start="2024-04-01",
            period_end="2025-03-31",
            normalized_value=9000,
            normalized_unit="INR crore",
            modality="forecast",
        )
    )

    assert {issue.code for issue in issues} >= {
        "number_not_in_evidence",
        "period_not_in_evidence",
    }


def test_fact_semantics_reject_bad_normalization_and_unsupported_date() -> None:
    issues = validate_fact_semantics(
        candidate(
            normalized_value=8142,
            as_of_date="2024-03-31",
            period_start=None,
            period_end=None,
        )
    )

    assert {issue.code for issue in issues} == {
        "date_not_in_evidence",
        "invalid_unit_conversion",
    }


def test_fact_semantics_reject_unsupported_identity_scope_and_comparison_key() -> None:
    issues = validate_fact_semantics(
        candidate(
            subject="Acme",
            predicate="employee headcount",
            scope=["Europe"],
            comparison_key="unrelated|profit after tax",
        ),
        document_name="delhivery-annual-report.pdf",
    )

    assert {issue.code for issue in issues} >= {
        "subject_not_in_evidence",
        "predicate_not_in_evidence",
        "scope_not_in_evidence",
        "comparison_key_mismatch",
    }


def test_relation_semantics_catches_impossible_numeric_labels() -> None:
    left = stored("left", 6.5)
    right = stored("right", 6.6)
    corroboration = RelationDecision(
        relation_type="corroborates",
        confidence=0.9,
        explanation="Both sources report the same value.",
        decisive_context=["same metric"],
    )

    issues = validate_relation_semantics(left, right, corroboration)

    assert [issue.code for issue in issues] == ["corroboration_value_conflict"]


def test_relation_semantics_rejects_corroboration_across_periods() -> None:
    left = stored("left", 6.5)
    right = stored("right", 6.5, period_end="2025-03-31")
    corroboration = RelationDecision(
        relation_type="corroborates",
        confidence=0.9,
        explanation="The values match, but the periods do not match.",
        decisive_context=["different periods"],
    )

    issues = validate_relation_semantics(left, right, corroboration)

    assert [issue.code for issue in issues] == ["corroboration_context_mismatch"]


def test_relation_semantics_compares_raw_values_when_normalized_values_are_missing() -> None:
    left = stored("left", 6.5).model_copy(
        update={"normalized_value": None, "normalized_unit": None}
    )
    right = stored("right", 6.6).model_copy(
        update={"normalized_value": None, "normalized_unit": None}
    )
    corroboration = RelationDecision(
        relation_type="corroborates",
        confidence=0.9,
        explanation="Both sources report the same value.",
        decisive_context=["same metric"],
    )

    issues = validate_relation_semantics(left, right, corroboration)

    assert [issue.code for issue in issues] == ["corroboration_value_conflict"]


def test_relation_semantics_compares_compatible_scaled_units() -> None:
    left = stored("left", 1.0).model_copy(
        update={
            "value_number": 1,
            "unit": "INR crore",
            "normalized_value": None,
            "normalized_unit": None,
        }
    )
    right = stored("right", 10.0).model_copy(
        update={
            "value_number": 10,
            "unit": "INR million",
            "normalized_value": None,
            "normalized_unit": None,
        }
    )
    corroboration = RelationDecision(
        relation_type="corroborates",
        confidence=0.9,
        explanation="Both sources report the same value in compatible units.",
        decisive_context=["equivalent scale"],
    )

    assert validate_relation_semantics(left, right, corroboration) == []


def test_relation_semantics_allows_rounding_at_the_coarser_reported_precision() -> None:
    annual_report = stored("annual", 81_415.38).model_copy(
        update={
            "object_text": "INR 81,415.38 million",
            "value_number": 81_415.38,
            "unit": "INR million",
            "normalized_value": None,
            "normalized_unit": None,
        }
    )
    presentation = stored("presentation", 8_142).model_copy(
        update={
            "object_text": "INR 8,142 crore",
            "value_number": 8_142,
            "unit": "INR crore",
            "normalized_value": None,
            "normalized_unit": None,
        }
    )
    corroboration = RelationDecision(
        relation_type="corroborates",
        confidence=0.9,
        explanation="The presentation rounds the annual report value to the nearest crore.",
        decisive_context=["rounding precision"],
    )

    assert validate_relation_semantics(annual_report, presentation, corroboration) == []
