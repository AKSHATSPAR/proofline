from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValueType(StrEnum):
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    ENTITY = "entity"
    TEXT = "text"


class Modality(StrEnum):
    ACTUAL = "actual"
    ESTIMATE = "estimate"
    FORECAST = "forecast"
    TARGET = "target"
    CLAIM = "claim"


class RelationType(StrEnum):
    CORROBORATES = "corroborates"
    CONTRADICTS = "contradicts"
    RECONCILES = "reconciles"
    UNRELATED = "unrelated"


class FactCandidate(StrictModel):
    """A dynamic claim shape returned by the extractor.

    Nullable fields are still required in the structured output. That makes the
    JSON schema strict while allowing facts that are not numeric or time-bound.
    """

    subject: str = Field(description="Entity the claim is about")
    predicate: str = Field(description="Short relation or metric name")
    object_text: str = Field(description="Value or object exactly as understood")
    value_type: ValueType
    value_number: float | None
    unit: str | None = Field(description="Unit written in the source")
    normalized_value: float | None = Field(
        description="Value converted to normalized_unit, without rounding invention"
    )
    normalized_unit: str | None
    period_start: str | None = Field(description="ISO date when supported, otherwise null")
    period_end: str | None = Field(description="ISO date when supported, otherwise null")
    as_of_date: str | None = Field(description="ISO date for point-in-time claims")
    scope: list[str] = Field(description="Material qualifiers such as consolidated or India")
    modality: Modality
    comparison_key: str = Field(
        description="Stable semantic key independent of formatting, unit, period, and scope"
    )
    evidence_quote: str = Field(
        min_length=12,
        description="A short verbatim quote containing the claim and enough context",
    )
    page_number: int = Field(ge=1, description="One-based PDF page carrying the quote")
    confidence: float = Field(ge=0, le=1)
    extraction_note: str | None


class FactBatch(StrictModel):
    facts: list[FactCandidate]


class RelationDecision(StrictModel):
    relation_type: RelationType
    confidence: float = Field(ge=0, le=1)
    explanation: str = Field(
        description="Concise reviewer-facing reasoning that cites value, time, scope, or unit"
    )
    decisive_context: list[str]


class Page(StrictModel):
    page_number: int
    text: str


class TextChunk(StrictModel):
    index: int
    pages: list[int]
    text: str


class StoredFact(FactCandidate):
    id: str
    document_id: str
    document_name: str
    chunk_index: int
    evidence_status: str
    extraction_method: str


class StoredRelation(RelationDecision):
    id: str
    left_fact_id: str
    right_fact_id: str
