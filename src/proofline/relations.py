from __future__ import annotations

from collections import defaultdict

from proofline.schemas import StoredFact
from proofline.semantics import semantic_tokens


def _fact_signature(fact: StoredFact) -> tuple[set[str], set[str]]:
    entity_tokens = semantic_tokens(fact.subject, entity=True)
    metric_tokens = semantic_tokens(f"{fact.comparison_key.replace('|', ' ')} {fact.predicate}")
    metric_tokens -= entity_tokens
    return entity_tokens, metric_tokens


def candidate_pairs(
    facts: list[StoredFact],
    limit_per_fact: int = 5,
    *,
    excluded_pairs: set[tuple[str, str]] | None = None,
) -> list[tuple[str, str]]:
    """Retrieve plausible pairs through an inverted metric-token index."""

    excluded_pairs = excluded_pairs or set()
    signatures = [_fact_signature(fact) for fact in facts]
    postings: dict[str, set[int]] = defaultdict(set)
    for index, (_, metric_tokens) in enumerate(signatures):
        for token in metric_tokens:
            postings[token].add(index)

    scored: list[tuple[float, str, str]] = []
    counts: dict[str, int] = defaultdict(int)
    for left_index, left in enumerate(facts):
        left_entity, left_metric = signatures[left_index]
        candidate_indexes: set[int] = set()
        for token in left_metric:
            candidate_indexes.update(postings[token])

        for right_index in candidate_indexes:
            if right_index <= left_index:
                continue
            right = facts[right_index]
            if left.document_id == right.document_id:
                continue
            right_entity, right_metric = signatures[right_index]
            if not left_entity or not right_entity or not (left_entity & right_entity):
                continue

            entity_score = len(left_entity & right_entity) / len(left_entity | right_entity)
            metric_score = len(left_metric & right_metric) / len(left_metric | right_metric)
            if entity_score < 0.34 or metric_score < 0.5:
                continue
            score = 0.35 * entity_score + 0.65 * metric_score
            scored.append((score, left.id, right.id))

    pairs: list[tuple[str, str]] = []
    for _, left_id, right_id in sorted(scored, key=lambda item: (-item[0], item[1], item[2])):
        if tuple(sorted((left_id, right_id))) in excluded_pairs:
            continue
        if counts[left_id] >= limit_per_fact or counts[right_id] >= limit_per_fact:
            continue
        pairs.append((left_id, right_id))
        counts[left_id] += 1
        counts[right_id] += 1
    return pairs
