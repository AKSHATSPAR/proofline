from __future__ import annotations

import re
from collections import defaultdict

from proofline.schemas import StoredFact

_TOKENS = re.compile(r"[a-z0-9]+")


def _tokens(value: str) -> set[str]:
    return set(_TOKENS.findall(value.lower()))


def _similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def candidate_pairs(facts: list[StoredFact], limit_per_fact: int = 5) -> list[tuple[str, str]]:
    """Block the quadratic comparison problem using the model-proposed semantic key."""

    by_document: dict[str, list[StoredFact]] = defaultdict(list)
    for fact in facts:
        by_document[fact.document_id].append(fact)

    document_ids = sorted(by_document)
    scored: list[tuple[float, str, str]] = []
    counts: dict[str, int] = defaultdict(int)
    for index, left_document in enumerate(document_ids):
        for right_document in document_ids[index + 1 :]:
            for left in by_document[left_document]:
                for right in by_document[right_document]:
                    key_score = _similarity(left.comparison_key, right.comparison_key)
                    label_score = _similarity(
                        f"{left.subject} {left.predicate}",
                        f"{right.subject} {right.predicate}",
                    )
                    score = max(key_score, label_score)
                    if score >= 0.5:
                        scored.append((score, left.id, right.id))

    pairs: list[tuple[str, str]] = []
    for _, left_id, right_id in sorted(scored, reverse=True):
        if counts[left_id] >= limit_per_fact or counts[right_id] >= limit_per_fact:
            continue
        pairs.append((left_id, right_id))
        counts[left_id] += 1
        counts[right_id] += 1
    return pairs
