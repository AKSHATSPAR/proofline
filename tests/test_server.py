from pathlib import Path

from fastapi.testclient import TestClient

from proofline.server import create_app


def test_demo_exposes_all_required_cases(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "api.db"))

    summary = client.get("/api/summary").json()
    relations = client.get("/api/relations").json()
    failures = client.get("/api/failures").json()

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


def test_page_evidence_and_no_key_upload_guard(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PROOFLINE_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(tmp_path / "api.db"))

    page = client.get("/api/documents/demo-economic-survey/pages/4")
    page_image = client.get("/api/documents/demo-economic-survey/pages/4/image")
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
    assert upload.status_code == 503
    assert "GEMINI_API_KEY" in upload.json()["detail"]
