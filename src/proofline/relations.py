from __future__ import annotations

import re
from collections import defaultdict

from proofline.schemas import StoredFact

_TOKENS = re.compile(r"[a-z0-9]+")
_PHRASE_ALIASES = (
    (re.compile(r"\bgross domestic product\b"), "gdp"),
    (re.compile(r"\beconomic growth\b"), "gdp growth"),
    (re.compile(r"\bconsumer price index\b"), "cpi"),
    (re.compile(r"\brevenue from operations\b"), "revenue"),
    (re.compile(r"\btotal income\b"), "revenue"),
    (re.compile(r"\bnet sales\b"), "revenue"),
    (re.compile(r"\bprofit after tax\b"), "pat"),
    (re.compile(r"\bnet profit\b"), "pat"),
    (re.compile(r"\bnet income\b"), "pat"),
)
_TOKEN_ALIASES = {
    "turnover": "revenue",
    "sales": "revenue",
    "clients": "customer",
    "client": "customer",
    "headcount": "employee",
    "personnel": "employee",
}
_STOPWORDS = {
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "the",
    "to",
    "total",
}
_ENTITY_SUFFIXES = {"co", "company", "corp", "corporation", "inc", "limited", "ltd", "plc", "pvt"}


def _tokens(value: str, *, entity: bool = False) -> set[str]:
    normalized = value.lower()
    for pattern, replacement in _PHRASE_ALIASES:
        normalized = pattern.sub(replacement, normalized)

    tokens: set[str] = set()
    for raw_token in _TOKENS.findall(normalized):
        token = _TOKEN_ALIASES.get(raw_token, raw_token)
        if token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
            token = token[:-1]
        if token in _STOPWORDS or (entity and token in _ENTITY_SUFFIXES):
            continue
        tokens.add(token)
    return tokens


def _fact_signature(fact: StoredFact) -> tuple[set[str], set[str]]:
    entity_tokens = _tokens(fact.subject, entity=True)
    metric_tokens = _tokens(f"{fact.comparison_key.replace('|', ' ')} {fact.predicate}")
    metric_tokens -= entity_tokens
    return entity_tokens, metric_tokens


def candidate_pairs(facts: list[StoredFact], limit_per_fact: int = 5) -> list[tuple[str, str]]:
    """Retrieve plausible pairs through an inverted metric-token index."""

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
        if counts[left_id] >= limit_per_fact or counts[right_id] >= limit_per_fact:
            continue
        pairs.append((left_id, right_id))
        counts[left_id] += 1
        counts[right_id] += 1
    return pairs
