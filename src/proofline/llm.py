from __future__ import annotations

import json
import os
import re
import time
from typing import Protocol

from google import genai
from google.genai.errors import APIError
from openai import OpenAI

from proofline.schemas import FactBatch, RelationDecision, StoredFact

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODELS = {
    "gemini": "gemini-3.7-flash",
    "openai": "gpt-5.4-mini",
}
PROVIDER_KEY_ENV = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
}

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


class Extractor(Protocol):
    provider: str
    model: str

    def extract(self, document_name: str, chunk_text: str) -> FactBatch: ...

    def compare(self, left: StoredFact, right: StoredFact) -> RelationDecision: ...


def provider_name(provider: str | None = None) -> str:
    resolved = (provider or os.getenv("PROOFLINE_PROVIDER", DEFAULT_PROVIDER)).strip().lower()
    if resolved not in DEFAULT_MODELS:
        supported = ", ".join(sorted(DEFAULT_MODELS))
        raise ValueError(f"Unsupported provider {resolved!r}; choose one of: {supported}")
    return resolved


def provider_model(provider: str | None = None, model: str | None = None) -> str:
    resolved_provider = provider_name(provider)
    environment_name = f"{resolved_provider.upper()}_MODEL"
    return model or os.getenv(environment_name, DEFAULT_MODELS[resolved_provider])


def provider_key_name(provider: str | None = None) -> str:
    return PROVIDER_KEY_ENV[provider_name(provider)]


def provider_is_configured(provider: str | None = None) -> bool:
    return bool(os.getenv(provider_key_name(provider)))


def create_extractor(provider: str | None = None, model: str | None = None) -> Extractor:
    resolved_provider = provider_name(provider)
    resolved_model = provider_model(resolved_provider, model)
    key_name = provider_key_name(resolved_provider)
    if not os.getenv(key_name):
        raise RuntimeError(f"Set {key_name} to process new PDFs with {resolved_provider}.")
    if resolved_provider == "gemini":
        return GeminiExtractor(model=resolved_model)
    return OpenAIExtractor(model=resolved_model)


class GeminiExtractor:
    provider = "gemini"

    def __init__(self, model: str = DEFAULT_MODELS["gemini"], client=None):
        self.model = model
        self.client = client or genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def _structured(self, instructions: str, input_text: str, output_type):
        for attempt in range(3):
            try:
                interaction = self.client.interactions.create(
                    model=self.model,
                    input=f"{instructions}\n\n{input_text}",
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": output_type.model_json_schema(),
                    },
                )
                return output_type.model_validate_json(interaction.output_text)
            except APIError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    raise
                retry_match = re.search(r"retry in ([0-9.]+)s", error.message or "", re.IGNORECASE)
                retry_seconds = (
                    float(retry_match.group(1)) + 0.5 if retry_match else 2 ** (attempt + 1)
                )
                time.sleep(min(retry_seconds, 30))

        raise RuntimeError("Gemini request exhausted its retry budget")

    def extract(self, document_name: str, chunk_text: str) -> FactBatch:
        return self._structured(
            EXTRACTION_INSTRUCTIONS,
            f"DOCUMENT: {document_name}\n\n{chunk_text}",
            FactBatch,
        )

    def compare(self, left: StoredFact, right: StoredFact) -> RelationDecision:
        left_payload = left.model_dump_json(
            exclude={"id", "document_id", "chunk_index", "evidence_status", "extraction_method"}
        )
        right_payload = right.model_dump_json(
            exclude={"id", "document_id", "chunk_index", "evidence_status", "extraction_method"}
        )
        return self._structured(
            RELATION_INSTRUCTIONS,
            f"LEFT FACT:\n{left_payload}\n\nRIGHT FACT:\n{right_payload}",
            RelationDecision,
        )


class OpenAIExtractor:
    provider = "openai"

    def __init__(self, model: str = DEFAULT_MODELS["openai"], client: OpenAI | None = None):
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
