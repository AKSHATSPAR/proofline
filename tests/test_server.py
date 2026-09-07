from pathlib import Path

from fastapi.testclient import TestClient

from proofline.server import create_app


def test_demo_exposes_all_required_cases(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "api.db"))

    summary = client.get("/api/summary").json()
    relations = client.get("/api/relations").json()
    failures = client.get("/api/failures").json()
    audit = client.get("/api/audits/grounding").json()

    assert summary == {
        "documents": 3,
        "facts": 6,
        "relations": 3,
        "failures": 1,
        "relation_types": {
            "corroborates": 1,
            "contradicts": 1,
            "reconciles": 1,
        },
    }
    assert {item["relation_type"] for item in relations} == {
        "corroborates",
        "contradicts",
        "reconciles",
    }
    assert failures[0]["stage"] == "table_header_binding"
    assert audit["accepted_facts"] == 6
    assert audit["page_grounded"] == 6
    assert audit["fields_grounded"] == 6
    assert audit["word_anchored"] == audit["source_available"]
    assert audit["unanchored_fact_ids"] == []


def test_page_evidence_and_no_key_upload_guard(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PROOFLINE_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    client = TestClient(create_app(tmp_path / "api.db"))

    page = client.get("/api/documents/demo-economic-survey/pages/4")
    page_image = client.get("/api/documents/demo-economic-survey/pages/4/image")
    evidence_image = client.get("/api/facts/fact-rbi-fy25-growth/evidence-image")
    upload = client.post(
        "/api/uploads",
        files=[("files", ("sample.pdf", b"%PDF-1.4\n", "application/pdf"))],
    )

    assert page.status_code == 200
    assert "first advance estimates" in page.json()["text"]
    if page_image.status_code == 200:
        assert page_image.headers["content-type"] == "image/png"
        assert page_image.content.startswith(b"\x89PNG")
    else:
        assert page_image.status_code == 404
    if evidence_image.status_code == 200:
        assert evidence_image.headers["content-type"] == "image/png"
        assert evidence_image.content.startswith(b"\x89PNG")
        assert int(evidence_image.headers["x-proofline-evidence-spans"]) > 0
        assert evidence_image.headers["x-proofline-evidence-status"] == "located"
    else:
        assert evidence_image.status_code == 404
    assert upload.status_code == 503
    assert "GEMINI_API_KEY" in upload.json()["detail"]
