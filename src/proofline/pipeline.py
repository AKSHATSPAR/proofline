from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from proofline.llm import OpenAIExtractor
from proofline.relations import candidate_pairs
from proofline.schemas import RelationType, StoredFact, StoredRelation
from proofline.store import Store
from proofline.text import build_chunks, extract_pages, verify_evidence

ProgressCallback = Callable[[str, int, int], None]


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    name: str
    page_count: int
    facts_added: int
    facts_rejected: int
    skipped: bool = False


class KnowledgeLayer:
    def __init__(self, store: Store, extractor: OpenAIExtractor):
        self.store = store
        self.extractor = extractor

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def ingest_pdf(self, pdf_path: Path, progress: ProgressCallback | None = None) -> IngestResult:
        sha256 = self._hash_file(pdf_path)
        existing = self.store.document_by_hash(sha256)
        if existing is not None:
            return IngestResult(
                document_id=existing["id"],
                name=existing["name"],
                page_count=existing["page_count"],
                facts_added=0,
                facts_rejected=0,
                skipped=True,
            )

        document_id = sha256[:16]
        pages = extract_pages(pdf_path)
        page_lookup = {page.page_number: page.text for page in pages}
        self.store.add_document(
            document_id,
            pdf_path.name,
            sha256,
            [(page.page_number, page.text) for page in pages],
        )

        chunks = build_chunks(pages)
        facts_added = 0
        facts_rejected = 0
        try:
            for position, chunk in enumerate(chunks, start=1):
                if progress:
                    progress(pdf_path.name, position, len(chunks))
                try:
                    batch = self.extractor.extract(pdf_path.name, chunk.text)
                # A bad API response must not discard facts accepted from earlier chunks.
                except Exception as error:  # noqa: BLE001
                    self.store.add_failure(
                        document_id,
                        "extraction",
                        str(error),
                        chunk_index=chunk.index,
                        details={"pages": chunk.pages},
                    )
                    continue

                for candidate in batch.facts:
                    if candidate.page_number not in chunk.pages:
                        facts_rejected += 1
                        self.store.add_failure(
                            document_id,
                            "evidence_validation",
                            "Claimed page was outside the source chunk",
                            page_number=candidate.page_number,
                            chunk_index=chunk.index,
                            details={"comparison_key": candidate.comparison_key},
                        )
                        continue
                    valid, evidence_status = verify_evidence(
                        candidate.evidence_quote, page_lookup[candidate.page_number]
                    )
                    if not valid:
                        facts_rejected += 1
                        self.store.add_failure(
                            document_id,
                            "evidence_validation",
                            "Model quote could not be anchored verbatim to the claimed page",
                            page_number=candidate.page_number,
                            chunk_index=chunk.index,
                            details={
                                "comparison_key": candidate.comparison_key,
                                "quote": candidate.evidence_quote,
                            },
                        )
                        continue

                    fact_id = hashlib.sha256(
                        (
                            f"{document_id}|{candidate.page_number}|"
                            f"{candidate.comparison_key}|{candidate.evidence_quote}"
                        ).encode()
                    ).hexdigest()[:20]
                    fact = StoredFact(
                        **candidate.model_dump(),
                        id=fact_id,
                        document_id=document_id,
                        document_name=pdf_path.name,
                        chunk_index=chunk.index,
                        evidence_status=evidence_status,
                        extraction_method=f"openai:{self.extractor.model}",
                    )
                    self.store.add_fact(fact)
                    facts_added += 1
        except Exception:
            self.store.set_document_status(document_id, "failed")
            raise

        self.store.set_document_status(document_id, "ready")
        return IngestResult(
            document_id=document_id,
            name=pdf_path.name,
            page_count=len(pages),
            facts_added=facts_added,
            facts_rejected=facts_rejected,
        )

    def discover_relations(self, max_pairs: int = 200) -> int:
        facts = self.store.facts()
        facts_by_id = {fact.id: fact for fact in facts}
        existing = {
            tuple(sorted((relation.left_fact_id, relation.right_fact_id)))
            for relation in self.store.relations()
        }
        added = 0
        for left_id, right_id in candidate_pairs(facts)[:max_pairs]:
            ordered = tuple(sorted((left_id, right_id)))
            if ordered in existing:
                continue
            left = facts_by_id[left_id]
            right = facts_by_id[right_id]
            try:
                decision = self.extractor.compare(left, right)
            # Candidate pairs are independent; preserve the rest when one call fails.
            except Exception as error:  # noqa: BLE001
                self.store.add_failure(
                    None,
                    "relation_classification",
                    str(error),
                    details={"left_fact_id": left_id, "right_fact_id": right_id},
                )
                continue
            if decision.relation_type == RelationType.UNRELATED:
                continue
            relation_id = hashlib.sha256(f"{left_id}|{right_id}".encode()).hexdigest()[:20]
            self.store.add_relation(
                StoredRelation(
                    **decision.model_dump(),
                    id=relation_id,
                    left_fact_id=left_id,
                    right_fact_id=right_id,
                )
            )
            existing.add(ordered)
            added += 1
        return added
