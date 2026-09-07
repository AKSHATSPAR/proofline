# Proofline

Proofline is a page-grounded fact knowledge layer for financial PDFs. It extracts atomic facts,
rejects claims whose quoted evidence cannot be found on the claimed PDF page, and classifies
cross-document relationships as corroboration, contradiction, or context-based reconciliation.

> Work in progress: the core ingestion library is implemented first. The review UI, curated
> Delhivery demo, complete setup guide, demo script, and evaluation notes will be added in the
> next chunks.

## Current architecture

1. PyMuPDF extracts page-separated text.
2. Page labels survive chunking, including for oversized pages.
3. An OpenAI structured-output call discovers dynamic, atomic facts.
4. Every returned evidence quote is checked against its claimed page before storage.
5. SQLite stores documents, pages, facts, relationships, and recoverable failures incrementally.
6. Semantic comparison keys block candidate pairs before a second structured-output call explains
   the relationship.

## Developer check

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

## Setup and Run Instructions

Coming in the UI chunk.

## Video Demo

To be recorded after the final local workflow is verified.

## Approach

Coming in the documentation chunk.

## Limitations and Next Steps

Coming in the documentation chunk.

## Additional Notes

The repository never stores API credentials. New-PDF processing will read `OPENAI_API_KEY` from
the local environment; a checked-in curated demo will remain inspectable without a key.
