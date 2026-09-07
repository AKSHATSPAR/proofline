import json
from types import SimpleNamespace

from google.genai.errors import ServerError

from proofline.llm import GeminiExtractor, provider_key_name, provider_model, provider_name
from proofline.schemas import StoredFact


class FakeInteractions:
    def __init__(self, payload: dict):
        self.payload = payload
        self.request = None

    def create(self, **request):
        self.request = request
        return SimpleNamespace(output_text=json.dumps(self.payload))


class FlakyInteractions(FakeInteractions):
    def __init__(self, payload: dict):
        super().__init__(payload)
        self.calls = 0

    def create(self, **request):
        self.calls += 1
        if self.calls == 1:
            raise ServerError(500, {"error": {"message": "temporary high demand"}})
        return super().create(**request)


class InteractionRateLimitError(Exception):
    status_code = 429

    def __init__(self) -> None:
        self.message = "Quota reached. Please retry in 25.5s."
        super().__init__(self.message)


class RateLimitedInteractions(FakeInteractions):
    def __init__(self, payload: dict):
        super().__init__(payload)
        self.calls = 0

    def create(self, **request):
        self.calls += 1
        if self.calls == 1:
            raise InteractionRateLimitError
        return super().create(**request)


def test_gemini_extractor_requests_schema_constrained_facts() -> None:
    interactions = FakeInteractions({"facts": []})
    client = SimpleNamespace(interactions=interactions)
    extractor = GeminiExtractor(model="gemini-test", client=client)

    result = extractor.extract("report.pdf", "[[PDF_PAGE 1]]\nRevenue rose 10%.")

    assert result.facts == []
    assert interactions.request["model"] == "gemini-test"
    assert interactions.request["response_format"]["mime_type"] == "application/json"
    assert interactions.request["response_format"]["schema"]["title"] == "FactBatch"
    assert "report.pdf" in interactions.request["input"]


def test_gemini_is_the_zero_cost_default(monkeypatch) -> None:
    monkeypatch.delenv("PROOFLINE_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    assert provider_name() == "gemini"
    assert provider_model() == "gemini-3.7-flash"
    assert provider_key_name() == "GEMINI_API_KEY"


def test_gemini_retries_transient_provider_errors(monkeypatch) -> None:
    interactions = FlakyInteractions({"facts": []})
    client = SimpleNamespace(interactions=interactions)
    monkeypatch.setattr("proofline.llm.time.sleep", lambda _: None)

    result = GeminiExtractor(model="gemini-test", client=client).extract("report.pdf", "text")

    assert result.facts == []
    assert interactions.calls == 2


def test_gemini_retries_interactions_rate_limit_and_honours_delay(monkeypatch) -> None:
    interactions = RateLimitedInteractions({"facts": []})
    client = SimpleNamespace(interactions=interactions)
    delays: list[float] = []
    monkeypatch.setattr("proofline.llm.time.sleep", delays.append)

    result = GeminiExtractor(model="gemini-test", client=client).extract("report.pdf", "text")

    assert result.facts == []
    assert interactions.calls == 2
    assert delays == [26.0]


def test_comparison_includes_bounded_source_context() -> None:
    interactions = FakeInteractions(
        {
            "relation_type": "corroborates",
            "confidence": 0.9,
            "explanation": "Both sources report the same revenue for the same period.",
            "decisive_context": ["same period", "same value"],
        }
    )
    extractor = GeminiExtractor(
        model="gemini-test", client=SimpleNamespace(interactions=interactions)
    )
    payload = {
        "document_name": "report.pdf",
        "chunk_index": 0,
        "subject": "Delhivery",
        "predicate": "revenue",
        "object_text": "100 crore",
        "value_type": "number",
        "value_number": 100,
        "unit": "INR crore",
        "normalized_value": 1000,
        "normalized_unit": "INR million",
        "period_start": "2023-04-01",
        "period_end": "2024-03-31",
        "as_of_date": None,
        "scope": ["consolidated"],
        "modality": "actual",
        "comparison_key": "delhivery|revenue",
        "evidence_quote": "Revenue was INR 100 crore in FY24.",
        "page_number": 1,
        "confidence": 0.9,
        "extraction_note": None,
        "evidence_status": "exact",
        "extraction_method": "test",
    }
    left = StoredFact(id="left", document_id="left-doc", **payload)
    right = StoredFact(id="right", document_id="right-doc", **payload)

    extractor.compare(
        left,
        right,
        left_context="The consolidated table uses INR crore.",
        right_context="The filing reports the same accounting basis.",
    )

    sent = interactions.request["input"]
    assert "LEFT SOURCE CONTEXT" in sent
    assert "The consolidated table uses INR crore." in sent
    assert "RIGHT SOURCE CONTEXT" in sent
