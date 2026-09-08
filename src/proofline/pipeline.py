from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from proofline.llm import Extractor
from proofline.relations import candidate_pairs
from proofline.schemas import RelationType, StoredFact, StoredRelation
from proofline.store import Store
from proofline.text import (
    build_chunks,
    evidence_context,
    extract_pages,
    normalize_whitespace,
    verify_evidence,
)
from proofline.validation import validate_fact_semantics, validate_relation_semantics

ProgressCallback = Callable[[str, int, int], None]
CHUNK_PIPELINE_REVISION = "fact-grounding-v2"


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    name: str
    page_count: int
    facts_added: int
    facts_rejected: int
    status: str = "ready"
    chunks_failed: int = 0
    chunks_empty: int = 0
    pages_unreadable: int = 0
    skipped: bool = False


class KnowledgeLayer:
    def __init__(self, store: Store, extractor: Extractor):
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
        if existing is not None and existing["status"] == "ready":
            return IngestResult(
                document_id=existing["id"],
                name=existing["name"],
                page_count=existing["page_count"],
                facts_added=0,
                facts_rejected=0,
                status="ready",
                skipped=True,
            )
        document_id = existing["id"] if existing is not None else sha256[:16]
        pages = extract_pages(pdf_path)
        page_lookup = {page.page_number: page.text for page in pages}
        if existing is None:
            self.store.add_document(
                document_id,
                pdf_path.name,
                sha256,
                [(page.page_number, page.text) for page in pages],
                source_path=str(pdf_path.resolve()),
            )
        else:
            self.store.resume_document(document_id, pdf_path.name, str(pdf_path.resolve()))

        unreadable_pages = [page for page in pages if not normalize_whitespace(page.text)]
        self.store.clear_document_failures(document_id, "page_extraction")
        for page in unreadable_pages:
            self.store.add_failure(
                document_id,
                "page_extraction",
                "No searchable text was found on this page",
                page_number=page.page_number,
                details={
                    "handling": "The page was skipped instead of being treated as an empty source.",
                    "next_step": "Run this page through OCR before extracting facts.",
                },
            )

        chunks = build_chunks(pages)
        fingerprints = {
            chunk.index: hashlib.sha256(
                f"{CHUNK_PIPELINE_REVISION}|{chunk.text}".encode()
            ).hexdigest()
            for chunk in chunks
        }
        facts_added = 0
        facts_rejected = 0
        try:
            for position, chunk in enumerate(chunks, start=1):
                if progress:
                    progress(pdf_path.name, position, len(chunks))
                if not self.store.start_chunk(document_id, chunk.index, fingerprints[chunk.index]):
                    continue
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
                    self.store.finish_chunk(document_id, chunk.index, "failed")
                    continue

                if not batch.facts:
                    self.store.add_failure(
                        document_id,
                        "empty_extraction",
                        "No candidate facts were returned for this source chunk",
                        chunk_index=chunk.index,
                        details={
                            "pages": chunk.pages,
                            "handling": "The empty result is visible for review instead of being treated as successful extraction.",
                            "next_step": "Review the source pages or retry with adjusted extraction instructions.",
                        },
                    )
                    self.store.finish_chunk(document_id, chunk.index, "empty")
                    continue

                accepted_in_chunk = 0
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

                    semantic_issues = validate_fact_semantics(
                        candidate,
                        support_text=evidence_context(
                            page_lookup[candidate.page_number], candidate.evidence_quote
                        ),
                        document_name=pdf_path.name,
                    )
                    if semantic_issues:
                        facts_rejected += 1
                        self.store.add_failure(
                            document_id,
                            "fact_validation",
                            "Structured fields were not supported by the evidence quote",
                            page_number=candidate.page_number,
                            chunk_index=chunk.index,
                            details={
                                "comparison_key": candidate.comparison_key,
                                "quote": candidate.evidence_quote,
                                "candidate": candidate.model_dump(mode="json"),
                                "issues": [issue.payload() for issue in semantic_issues],
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
                        extraction_method=f"{self.extractor.provider}:{self.extractor.model}",
                    )
                    if self.store.add_fact(fact):
                        facts_added += 1
                        accepted_in_chunk += 1
                self.store.finish_chunk(
                    document_id,
                    chunk.index,
                    "complete" if accepted_in_chunk else "rejected",
                )
        except Exception:
            self.store.set_document_status(document_id, "failed")
            raise

        chunk_states = self.store.chunk_statuses(document_id, fingerprints)
        chunks_failed = sum(status == "failed" for status in chunk_states.values())
        chunks_empty = sum(status == "empty" for status in chunk_states.values())
        chunks_complete = sum(status == "complete" for status in chunk_states.values())
        chunks_rejected = sum(status == "rejected" for status in chunk_states.values())
        terminal_chunks = chunks_complete + chunks_rejected

        if not chunks or chunks_failed == len(chunks):
            status = "failed"
        elif chunks_empty == len(chunks):
            status = "empty"
        elif chunks_rejected == len(chunks) and not unreadable_pages:
            status = "rejected"
        elif terminal_chunks < len(chunks) or unreadable_pages:
            status = "partial"
        else:
            status = "ready"
        self.store.set_document_status(document_id, status)
        return IngestResult(
            document_id=document_id,
            name=pdf_path.name,
            page_count=len(pages),
            facts_added=facts_added,
            facts_rejected=facts_rejected,
            status=status,
            chunks_failed=chunks_failed,
            chunks_empty=chunks_empty,
            pages_unreadable=len(unreadable_pages),
        )

    def discover_relations(self, max_pairs: int = 200) -> int:
        facts = self.store.facts()
        facts_by_id = {fact.id: fact for fact in facts}
        existing = {
            tuple(sorted((relation.left_fact_id, relation.right_fact_id)))
            for relation in self.store.relations()
        }
        completed = existing | self.store.checked_relation_pairs()
        pairs = candidate_pairs(facts, excluded_pairs=completed)[:max_pairs]
        comparisons = []
        for left_id, right_id in pairs:
            left = facts_by_id[left_id]
            right = facts_by_id[right_id]
            left_context = evidence_context(
                self.store.page_text(left.document_id, left.page_number) or "",
                left.evidence_quote,
            )
            right_context = evidence_context(
                self.store.page_text(right.document_id, right.page_number) or "",
                right.evidence_quote,
            )
            comparisons.append((left, right, left_context, right_context))

        decisions = []
        compare_many = getattr(self.extractor, "compare_many", None)
        if comparisons and callable(compare_many):
            try:
                batch = compare_many(comparisons)
            except Exception as error:  # noqa: BLE001
                self.store.add_failure(
                    None,
                    "relation_classification",
                    str(error),
                    details={"pair_count": len(comparisons)},
                )
                return 0
            by_index = {
                decision.pair_index: decision
                for decision in batch.decisions
                if decision.pair_index < len(pairs)
            }
            for index, pair in enumerate(pairs):
                decision = by_index.get(index)
                if decision is None:
                    self.store.add_failure(
                        None,
                        "relation_classification",
                        "The batch response omitted a candidate pair",
                        details={"left_fact_id": pair[0], "right_fact_id": pair[1]},
                    )
                    continue
                decisions.append((pair, decision))
        else:
            # Small test adapters and third-party implementations can retain the
            # one-pair method without losing compatibility.
            for pair, (left, right, left_context, right_context) in zip(
                pairs, comparisons, strict=True
            ):
                try:
                    decision = self.extractor.compare(
                        left,
                        right,
                        left_context=left_context,
                        right_context=right_context,
                    )
                except Exception as error:  # noqa: BLE001
                    self.store.add_failure(
                        None,
                        "relation_classification",
                        str(error),
                        details={"left_fact_id": pair[0], "right_fact_id": pair[1]},
                    )
                    continue
                decisions.append((pair, decision))

        added = 0
        for (left_id, right_id), decision in decisions:
            ordered = tuple(sorted((left_id, right_id)))
            left = facts_by_id[left_id]
            right = facts_by_id[right_id]
            semantic_issues = validate_relation_semantics(left, right, decision)
            if semantic_issues:
                self.store.mark_relation_checked(left_id, right_id, "rejected")
                self.store.add_failure(
                    None,
                    "relation_validation",
                    "The proposed relationship conflicted with deterministic fact fields",
                    details={
                        "left_fact_id": left_id,
                        "right_fact_id": right_id,
                        "proposed_relation": decision.relation_type.value,
                        "issues": [issue.payload() for issue in semantic_issues],
                    },
                )
                continue
            if decision.relation_type == RelationType.UNRELATED:
                self.store.mark_relation_checked(left_id, right_id, "unrelated")
                continue
            relation_id = hashlib.sha256(f"{left_id}|{right_id}".encode()).hexdigest()[:20]
            self.store.add_relation(
                StoredRelation(
                    **decision.model_dump(exclude={"pair_index"}),
                    id=relation_id,
                    left_fact_id=left_id,
                    right_fact_id=right_id,
                )
            )
            existing.add(ordered)
            completed.add(ordered)
            added += 1
        return added
