from __future__ import annotations

import json
from pathlib import Path

from proofline.schemas import StoredFact, StoredRelation
from proofline.store import Store
from proofline.text import evidence_context, verify_evidence
from proofline.validation import validate_fact_semantics, validate_relation_semantics

DEMO_PATH = Path(__file__).parent / "examples" / "india_macroeconomy_demo.json"
DEMO_DOCUMENT_IDS = {
    "demo-economic-survey",
    "demo-rbi-annual-report",
    "demo-imf-article-iv",
}


def load_demo(store: Store, path: Path = DEMO_PATH) -> bool:
    """Load or repair the source-verified sample without duplicating its audit rows."""

    payload = json.loads(path.read_text())
    changed = False
    page_lookup: dict[tuple[str, int], str] = {}
    document_ids: dict[str, str] = {}
    for document in payload["documents"]:
        source_candidate = path.parent / "sources" / Path(document["relative_source"]).name
        source_path = str(source_candidate) if source_candidate.exists() else None
        page_texts = [(item["page_number"], item["text"]) for item in document["pages"]]
        for page_number, text in page_texts:
            page_lookup[(document["id"], page_number)] = text
        existing_id = store.document(document["id"])
        if existing_id is not None and existing_id["sha256"] != document["sha256"]:
            store.delete_document(document["id"])
            existing_id = None
            changed = True
        existing_hash = store.document_by_hash(document["sha256"])
        if existing_hash is None:
            store.add_document(
                document["id"],
                document["name"],
                document["sha256"],
                page_texts,
                page_count=document["page_count"],
                source_path=source_path,
            )
            store.set_document_status(document["id"], "ready")
            document_ids[document["id"]] = document["id"]
            changed = True
        else:
            document_ids[document["id"]] = existing_hash["id"]

    for fact_payload in payload["facts"]:
        fact = StoredFact.model_validate(fact_payload)
        valid, status = verify_evidence(
            fact.evidence_quote,
            page_lookup[(fact.document_id, fact.page_number)],
        )
        if not valid or status != "exact":
            raise ValueError(f"Demo fact {fact.id} is not anchored to its page text")
        page_text = page_lookup[(fact.document_id, fact.page_number)]
        semantic_issues = validate_fact_semantics(
            fact,
            support_text=evidence_context(page_text, fact.evidence_quote),
            document_name=fact.document_name,
        )
        if semantic_issues:
            codes = ", ".join(issue.code for issue in semantic_issues)
            raise ValueError(f"Demo fact {fact.id} failed semantic validation: {codes}")
        fact = fact.model_copy(update={"document_id": document_ids[fact.document_id]})
        changed = store.add_fact(fact) or changed

    facts_by_id = {fact.id: fact for fact in store.facts()}
    for relation_payload in payload["relations"]:
        relation = StoredRelation.model_validate(relation_payload)
        left = facts_by_id[relation.left_fact_id]
        right = facts_by_id[relation.right_fact_id]
        issues = validate_relation_semantics(left, right, relation)
        if issues:
            codes = ", ".join(issue.code for issue in issues)
            raise ValueError(f"Demo relation {relation.id} failed semantic validation: {codes}")
        store.add_relation(relation)

    for failure in payload["failures"]:
        document_id = document_ids.get(failure["document_id"], failure["document_id"])
        if store.failure_exists(
            document_id,
            failure["stage"],
            failure["message"],
            page_number=failure.get("page_number"),
            chunk_index=failure.get("chunk_index"),
        ):
            continue
        store.clear_document_failures(document_id, failure["stage"])
        store.add_failure(
            document_id,
            failure["stage"],
            failure["message"],
            page_number=failure.get("page_number"),
            chunk_index=failure.get("chunk_index"),
            recoverable=failure["recoverable"],
            details=failure["details"],
        )
        changed = True
    return changed
