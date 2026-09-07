import json
from types import SimpleNamespace

from proofline.llm import GeminiExtractor, provider_key_name, provider_model, provider_name


class FakeInteractions:
    def __init__(self, payload: dict):
        self.payload = payload
        self.request = None

    def create(self, **request):
        self.request = request
        return SimpleNamespace(output_text=json.dumps(self.payload))


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
    assert provider_model() == "gemini-3.8-flash"
    assert provider_key_name() == "GEMINI_API_KEY"
