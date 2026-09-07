import json
from pathlib import Path

import pytest

from proofline.demo import DEMO_PATH
from proofline.relations import candidate_pairs
from proofline.schemas import StoredFact
from proofline.text import extract_pages, verify_evidence


def test_curated_facts_match_the_original_pdf_pages() -> None:
    project_root = Path(__file__).resolve().parents[1]
    payload = json.loads(DEMO_PATH.read_text())
    documents = {document["id"]: document for document in payload["documents"]}
    source_paths = {
        document_id: project_root / document["relative_source"]
        for document_id, document in documents.items()
    }
    if not all(path.exists() for path in source_paths.values()):
        pytest.skip("Starter PDFs are not bundled with the repository")

    extracted = {
        document_id: {page.page_number: page.text for page in extract_pages(path)}
        for document_id, path in source_paths.items()
    }
    for fact_payload in payload["facts"]:
        fact = StoredFact.model_validate(fact_payload)
        valid, status = verify_evidence(
            fact.evidence_quote,
            extracted[fact.document_id][fact.page_number],
        )
        assert (valid, status) == (True, "exact"), fact.id


def test_candidate_retrieval_keeps_every_required_demo_relationship() -> None:
    payload = json.loads(DEMO_PATH.read_text())
    facts = [StoredFact.model_validate(item) for item in payload["facts"]]
    retrieved = {frozenset(pair) for pair in candidate_pairs(facts)}
    required = {
        frozenset((relation["left_fact_id"], relation["right_fact_id"]))
        for relation in payload["relations"]
    }

    assert required <= retrieved
