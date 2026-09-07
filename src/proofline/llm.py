from __future__ import annotations

import json

from openai import OpenAI

from proofline.schemas import FactBatch, RelationDecision, StoredFact

EXTRACTION_INSTRUCTIONS = """You extract useful, atomic facts from financial and corporate documents.

Rules:
- Extract only decision-useful numerical or semantic claims explicitly supported by the supplied text.
- Each fact must be atomic: one subject, predicate, and object.
- Copy evidence_quote verbatim from exactly one labelled PDF page. Include enough nearby words to
  disambiguate the number or statement. Never repair OCR or invent wording in the quote.
- page_number must match the [[PDF_PAGE N]] label containing the quote.
- Preserve time, scope, accounting basis, and modality. Put material qualifiers in scope.
- Normalize units only when conversion is certain (for example 1 crore INR = 10 million INR).
  Otherwise leave normalized_value and normalized_unit null.
- comparison_key is a lowercase pipe-separated semantic identity such as
  "delhivery|revenue from customers". It must omit period, scope, unit, and formatting so potentially
  conflicting claims become candidates for comparison. Do not force unrelated metrics into one key.
- Prefer precision over recall. Skip boilerplate, isolated table fragments, page numbers, and claims
  whose header or unit is ambiguous.
"""


RELATION_INSTRUCTIONS = """Compare two page-grounded facts from different documents.

Choose exactly one:
- corroborates: materially the same claim after safe normalization.
- contradicts: same subject, metric, period, scope, and modality but incompatible values/statements.
- reconciles: the surface claims differ, but time, scope, unit, definition, or modality explains why.
- unrelated: not meaningfully comparable or there is not enough evidence.

Be sceptical. Different periods alone normally reconcile rather than contradict. Forecasts from different
publication vintages may genuinely disagree if they target the same period; mention the vintage. Explain
the decision using only fields and evidence supplied here. Do not claim access to the full source.
"""


class OpenAIExtractor:
    def __init__(self, model: str = "gpt-5.4-mini", client: OpenAI | None = None):
        self.model = model
        self.client = client or OpenAI()

    @staticmethod
    def _format(model_type: type[FactBatch | RelationDecision], name: str) -> dict:
        return {
            "type": "json_schema",
            "name": name,
            "strict": True,
            "schema": model_type.model_json_schema(),
        }

    def extract(self, document_name: str, chunk_text: str) -> FactBatch:
        response = self.client.responses.create(
            model=self.model,
            instructions=EXTRACTION_INSTRUCTIONS,
            input=f"DOCUMENT: {document_name}\n\n{chunk_text}",
            reasoning={"effort": "low"},
            text={"format": self._format(FactBatch, "fact_batch")},
            store=False,
        )
        return FactBatch.model_validate(json.loads(response.output_text))

    def compare(self, left: StoredFact, right: StoredFact) -> RelationDecision:
        left_payload = left.model_dump_json(
            exclude={"id", "document_id", "chunk_index", "evidence_status", "extraction_method"}
        )
        right_payload = right.model_dump_json(
            exclude={"id", "document_id", "chunk_index", "evidence_status", "extraction_method"}
        )
        response = self.client.responses.create(
            model=self.model,
            instructions=RELATION_INSTRUCTIONS,
            input=f"LEFT FACT:\n{left_payload}\n\nRIGHT FACT:\n{right_payload}",
            reasoning={"effort": "low"},
            text={"format": self._format(RelationDecision, "relation_decision")},
            store=False,
        )
        return RelationDecision.model_validate(json.loads(response.output_text))
