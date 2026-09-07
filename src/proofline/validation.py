from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from datetime import date

from proofline.schemas import FactCandidate, Modality, RelationDecision, RelationType, StoredFact

_PAREN_NUMBER = re.compile(r"\(\s*(\d[\d,]*(?:\.\d+)?)\s*%?\)")
_PLAIN_NUMBER = re.compile(r"(?<![A-Za-z])[-+−]?\s*\d[\d,]*(?:\.\d+)?")

_UNIT_PATTERNS = {
    "percent": re.compile(r"%|\bpercent\b|\bper\s+cent\b", re.IGNORECASE),
    "crore": re.compile(r"\bcrores?\b|(?<![A-Za-z])cr\b", re.IGNORECASE),
    "lakh": re.compile(r"\blakhs?\b|\blacs?\b", re.IGNORECASE),
    "billion": re.compile(r"\bbillions?\b|(?<![A-Za-z])bn\b", re.IGNORECASE),
    "million": re.compile(r"\bmillions?\b|(?<![A-Za-z])mn\b", re.IGNORECASE),
    "thousand": re.compile(r"\bthousands?\b|(?<![A-Za-z])k\b", re.IGNORECASE),
    "inr": re.compile(r"₹|\binr\b|\brs\.?\b|\brupees?\b", re.IGNORECASE),
    "usd": re.compile(r"\busd\b|\bus\s+dollars?\b|\bdollars?\b|\$", re.IGNORECASE),
    "ton": re.compile(r"\btonnes?\b|\btons?\b", re.IGNORECASE),
}

_SCALE = {
    "crore": 10_000_000,
    "lakh": 100_000,
    "billion": 1_000_000_000,
    "million": 1_000_000,
    "thousand": 1_000,
    "percent": 1,
}

_MODALITY_PATTERNS = {
    Modality.FORECAST: re.compile(
        r"\b(project(?:ed|ion)?|forecast|expect(?:ed|s)?|outlook|guidance|anticipat(?:ed|es))\b",
        re.IGNORECASE,
    ),
    Modality.ESTIMATE: re.compile(
        r"\b(estimat(?:e|ed|es)|provisional|advance estimate)\b", re.IGNORECASE
    ),
    Modality.TARGET: re.compile(r"\b(target|aim|goal)\b", re.IGNORECASE),
}


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    field: str
    message: str

    def payload(self) -> dict[str, str]:
        return asdict(self)


def _numbers(value: str) -> list[float]:
    numbers = [-float(match.group(1).replace(",", "")) for match in _PAREN_NUMBER.finditer(value)]
    without_parenthesized = _PAREN_NUMBER.sub(" ", value)
    for match in _PLAIN_NUMBER.finditer(without_parenthesized):
        token = match.group(0).replace(",", "").replace("−", "-").replace(" ", "")
        numbers.append(float(token))
    return numbers


def _contains_number(value: str, expected: float) -> bool:
    return any(
        math.isclose(number, expected, rel_tol=1e-9, abs_tol=1e-9) for number in _numbers(value)
    )


def _unit_kinds(value: str | None) -> set[str]:
    if not value:
        return set()
    return {name for name, pattern in _UNIT_PATTERNS.items() if pattern.search(value)}


def _scale(value: str | None) -> float | None:
    kinds = _unit_kinds(value)
    scales = [factor for name, factor in _SCALE.items() if name in kinds]
    return scales[0] if len(scales) == 1 else None


def _currency(value: str | None) -> str | None:
    kinds = _unit_kinds(value)
    if "inr" in kinds:
        return "inr"
    if "usd" in kinds:
        return "usd"
    return None


def _period_supported(start: str, end: str, quote: str) -> bool:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    compact = re.sub(r"\s+", "", quote.casefold())

    fiscal_quarters = {
        ((4, 1), (6, 30)): ("q1", start_date.year + 1),
        ((7, 1), (9, 30)): ("q2", start_date.year + 1),
        ((10, 1), (12, 31)): ("q3", start_date.year + 1),
        ((1, 1), (3, 31)): ("q4", end_date.year),
    }
    quarter = fiscal_quarters.get(
        ((start_date.month, start_date.day), (end_date.month, end_date.day))
    )
    if quarter:
        quarter_name, fiscal_end_year = quarter
        short_year = str(fiscal_end_year)[-2:]
        quarter_forms = {
            f"{quarter_name}fy{short_year}",
            f"{quarter_name}fy{fiscal_end_year}",
            f"{quarter_name}of{fiscal_end_year}",
        }
        return any(form in compact for form in quarter_forms)

    if start_date.year == end_date.year:
        return str(start_date.year) in compact

    start_year = start_date.year
    end_year = end_date.year
    short_end = str(end_year)[-2:]
    forms = {
        f"{start_year}-{short_end}",
        f"{start_year}/{short_end}",
        f"{start_year}-{end_year}",
        f"{start_year}/{end_year}",
        f"fy{short_end}",
        f"fy{start_year}-{short_end}",
        f"fy{start_year}/{short_end}",
        f"fy{start_year}-{end_year}",
        f"fy{start_year}/{end_year}",
    }
    return any(form in compact for form in forms)


def _date_supported(value: str, quote: str) -> bool:
    parsed = date.fromisoformat(value)
    month = parsed.strftime("%B").casefold()
    month_short = parsed.strftime("%b").casefold()
    compact = re.sub(r"[,\s]+", " ", quote.casefold()).strip()
    forms = {
        value.casefold(),
        f"{parsed.day:02d}-{parsed.month:02d}-{parsed.year}",
        f"{parsed.day:02d}/{parsed.month:02d}/{parsed.year}",
        f"{parsed.month:02d}/{parsed.day:02d}/{parsed.year}",
        f"{parsed.day} {month} {parsed.year}",
        f"{parsed.day} {month_short} {parsed.year}",
        f"{month} {parsed.day} {parsed.year}",
        f"{month_short} {parsed.day} {parsed.year}",
    }
    return any(form in compact or form in quote.casefold() for form in forms)


def validate_fact_semantics(candidate: FactCandidate) -> list[ValidationIssue]:
    """Check structured fields that can be proven directly from the evidence quote."""

    issues: list[ValidationIssue] = []
    quote = candidate.evidence_quote

    if candidate.value_type == "number":
        if candidate.value_number is None:
            issues.append(
                ValidationIssue(
                    "missing_numeric_value",
                    "value_number",
                    "A numeric fact must include value_number.",
                )
            )
        elif not _contains_number(quote, candidate.value_number):
            issues.append(
                ValidationIssue(
                    "number_not_in_evidence",
                    "value_number",
                    f"The value {candidate.value_number:g} does not appear in the evidence quote.",
                )
            )

    source_unit_kinds = _unit_kinds(candidate.unit)
    quote_unit_kinds = _unit_kinds(quote)
    missing_unit_kinds = source_unit_kinds - quote_unit_kinds
    if missing_unit_kinds:
        issues.append(
            ValidationIssue(
                "unit_not_in_evidence",
                "unit",
                f"The evidence quote does not show: {', '.join(sorted(missing_unit_kinds))}.",
            )
        )

    if (candidate.period_start is None) != (candidate.period_end is None):
        issues.append(
            ValidationIssue(
                "incomplete_period",
                "period_start",
                "A period must have both a start and an end date.",
            )
        )
    elif candidate.period_start and candidate.period_end:
        try:
            supported = _period_supported(candidate.period_start, candidate.period_end, quote)
        except ValueError:
            supported = False
        if not supported:
            issues.append(
                ValidationIssue(
                    "period_not_in_evidence",
                    "period_start",
                    "The stored period is not stated in the evidence quote.",
                )
            )

    if candidate.as_of_date:
        try:
            supported = _date_supported(candidate.as_of_date, quote)
        except ValueError:
            supported = False
        if not supported:
            issues.append(
                ValidationIssue(
                    "date_not_in_evidence",
                    "as_of_date",
                    "The stored as-of date is not stated in the evidence quote.",
                )
            )

    detected_modalities = {
        modality for modality, pattern in _MODALITY_PATTERNS.items() if pattern.search(quote)
    }
    if detected_modalities and candidate.modality not in detected_modalities:
        labels = ", ".join(sorted(modality.value for modality in detected_modalities))
        issues.append(
            ValidationIssue(
                "modality_conflict",
                "modality",
                f"The quote reads as {labels}, not {candidate.modality.value}.",
            )
        )

    if (candidate.normalized_value is None) != (candidate.normalized_unit is None):
        issues.append(
            ValidationIssue(
                "incomplete_normalization",
                "normalized_value",
                "A normalized value and normalized unit must be provided together.",
            )
        )
    elif (
        candidate.value_number is not None
        and candidate.normalized_value is not None
        and candidate.unit
        and candidate.normalized_unit
    ):
        source_currency = _currency(candidate.unit)
        normalized_currency = _currency(candidate.normalized_unit)
        if source_currency and normalized_currency and source_currency != normalized_currency:
            issues.append(
                ValidationIssue(
                    "currency_conversion_not_allowed",
                    "normalized_unit",
                    "Currency conversion is not supported by the deterministic validator.",
                )
            )
        source_scale = _scale(candidate.unit)
        normalized_scale = _scale(candidate.normalized_unit)
        if source_scale is not None and normalized_scale is not None:
            expected = candidate.value_number * source_scale / normalized_scale
            if not math.isclose(expected, candidate.normalized_value, rel_tol=1e-6, abs_tol=1e-9):
                issues.append(
                    ValidationIssue(
                        "invalid_unit_conversion",
                        "normalized_value",
                        f"The normalized value should be {expected:g} for the stated units.",
                    )
                )

    return issues


def validate_relation_semantics(
    left: StoredFact, right: StoredFact, decision: RelationDecision
) -> list[ValidationIssue]:
    """Reject relation labels that conflict with deterministic numeric or temporal fields."""

    issues: list[ValidationIssue] = []
    same_period = (left.period_start, left.period_end, left.as_of_date) == (
        right.period_start,
        right.period_end,
        right.as_of_date,
    )
    same_modality = left.modality == right.modality
    comparable_numbers = (
        left.normalized_value is not None
        and right.normalized_value is not None
        and left.normalized_unit == right.normalized_unit
    )
    same_value = comparable_numbers and math.isclose(
        left.normalized_value or 0,
        right.normalized_value or 0,
        rel_tol=1e-6,
        abs_tol=1e-9,
    )

    if (
        decision.relation_type == RelationType.CORROBORATES
        and comparable_numbers
        and not same_value
    ):
        issues.append(
            ValidationIssue(
                "corroboration_value_conflict",
                "relation_type",
                "Corroborating numeric facts must have equal normalized values.",
            )
        )
    if decision.relation_type == RelationType.CORROBORATES and (
        not same_period or not same_modality
    ):
        issues.append(
            ValidationIssue(
                "corroboration_context_mismatch",
                "relation_type",
                "Corroboration requires the same period and modality.",
            )
        )
    if decision.relation_type == RelationType.CONTRADICTS:
        if comparable_numbers and same_value:
            issues.append(
                ValidationIssue(
                    "contradiction_values_equal",
                    "relation_type",
                    "Equal normalized values cannot be a numeric contradiction.",
                )
            )
        if not same_period or not same_modality:
            issues.append(
                ValidationIssue(
                    "contradiction_context_mismatch",
                    "relation_type",
                    "A contradiction requires the same period and modality.",
                )
            )
    return issues
