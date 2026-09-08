from __future__ import annotations

import re

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
PHRASE_ALIASES = (
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
TOKEN_ALIASES = {
    "turnover": "revenue",
    "sales": "revenue",
    "grow": "growth",
    "grew": "growth",
    "grown": "growth",
    "indian": "india",
    "clients": "customer",
    "client": "customer",
    "headcount": "employee",
    "personnel": "employee",
}
STOPWORDS = {
    "a",
    "an",
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
ENTITY_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "limited",
    "ltd",
    "plc",
    "pvt",
}


def semantic_tokens(value: str, *, entity: bool = False) -> set[str]:
    """Return stable tokens for lightweight entity and financial metric matching."""

    normalized = value.lower()
    for pattern, replacement in PHRASE_ALIASES:
        normalized = pattern.sub(replacement, normalized)

    tokens: set[str] = set()
    for raw_token in TOKEN_PATTERN.findall(normalized):
        token = TOKEN_ALIASES.get(raw_token, raw_token)
        if token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
            token = token[:-1]
        if token in STOPWORDS or (entity and token in ENTITY_SUFFIXES):
            continue
        tokens.add(token)
    return tokens


def support_ratio(expected: str, source: str, *, entity: bool = False) -> float:
    expected_tokens = semantic_tokens(expected, entity=entity)
    if not expected_tokens:
        return 1.0
    source_tokens = semantic_tokens(source, entity=entity)
    return len(expected_tokens & source_tokens) / len(expected_tokens)
