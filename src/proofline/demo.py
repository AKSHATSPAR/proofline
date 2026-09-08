from __future__ import annotations

import json
from pathlib import Path

from proofline.schemas import StoredFact, StoredRelation
from proofline.store import Store
from proofline.text import verify_evidence
from proofline.validation import validate_fact_semantics

DEMO_PATH = Path(__file__).parent / "examples" / "india_macroeconomy_demo.json"


def load_demo(store: Store, path: Path = DEMO_PATH) -> bool:
    """Load source-verified sample output. Returns False when it was already present."""

    payload = json.loads(path.read_text())
    if all(store.document_by_hash(item["sha256"]) for item in payload["documents"]):
        return False

    page_lookup: dict[tuple[str, int], str] = {}
    for document in payload["documents"]:
        source_candidate = DEMO_PATH.parent / "sources" / Path(document["relative_source"]).name
        source_path = str(source_candidate) if source_candidate.exists() else None
        page_texts = [(item["page_number"], item["text"]) for item in document["pages"]]
        for page_number, text in page_texts:
            page_lookup[(document["id"], page_number)] = text
        if store.document_by_hash(document["sha256"]) is None:
            store.add_document(
                document["id"],
                document["name"],
                document["sha256"],
                page_texts,
                page_count=document["page_count"],
                source_path=source_path,
            )
            store.set_document_status(document["id"], "ready")

    for fact_payload in payload["facts"]:
        fact = StoredFact.model_validate(fact_payload)
        valid, status = verify_evidence(
            fact.evidence_quote,
            page_lookup[(fact.document_id, fact.page_number)],
        )
        if not valid or status != "exact":
            raise ValueError(f"Demo fact {fact.id} is not anchored to its page text")
        semantic_issues = validate_fact_semantics(fact)
        if semantic_issues:
            codes = ", ".join(issue.code for issue in semantic_issues)
            raise ValueError(f"Demo fact {fact.id} failed semantic validation: {codes}")
        store.add_fact(fact)

    for relation_payload in payload["relations"]:
        store.add_relation(StoredRelation.model_validate(relation_payload))

    for failure in payload["failures"]:
        store.add_failure(
            failure["document_id"],
            failure["stage"],
            failure["message"],
            page_number=failure.get("page_number"),
            chunk_index=failure.get("chunk_index"),
            recoverable=failure["recoverable"],
            details=failure["details"],
        )
    return True
