import json
from types import SimpleNamespace

from google.genai.errors import ServerError

from proofline.llm import GeminiExtractor, provider_key_name, provider_model, provider_name


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
