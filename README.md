# Proofline

Proofline is a page-grounded fact knowledge layer for financial PDFs. It extracts atomic claims,
rejects evidence it cannot verify, and explains whether cross-document facts corroborate,
contradict, or reconcile through context.

The repository opens with a source-verified India macroeconomy demo, so the complete review
experience works without credentials. An OpenAI API key is only needed to process new PDFs.

## Setup and Run Instructions

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run proofline-serve
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The curated demo loads automatically.
Interactive API documentation is available at
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

To process additional PDFs:

```bash
cp .env.example .env
# Add OPENAI_API_KEY to .env, then restart the server.
uv run proofline-serve
```

The UI accepts several PDFs at once and processes them in a background job. The CLI uses the same
pipeline:

```bash
uv run proofline path/to/one.pdf path/to/two.pdf
```

Run the checks with:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Video Demo

The final 3-minute demo link will be added after recording. A concise recording script is included
in [`docs/demo-script.md`](docs/demo-script.md).

## Approach

### Pipeline

```text
PDF upload
   -> content hash / incremental skip
   -> page-separated PyMuPDF extraction
   -> page-labelled, bounded chunks
   -> structured fact discovery
   -> verbatim evidence gate
   -> SQLite fact register
   -> semantic candidate blocking
   -> relationship adjudication + explanation
   -> API and review UI
```

The fact schema is intentionally dynamic. Rather than a fixed financial table, each atomic fact has
a subject, predicate, typed value, original and normalized units, period or as-of date, scope,
modality, confidence, semantic comparison key, and a short source quote. New predicates can appear
without a database migration.

### Grounding before reasoning

The extractor must return a verbatim quote and one-based PDF page. Whitespace is normalized, then
the quote is checked against text extracted from that exact page. If it cannot be anchored, the
candidate becomes a diagnostic rather than a fact. This deliberately trades some recall for a fact
layer a reviewer can audit.

### Cross-document comparison

The model emits a period- and unit-independent comparison key. Lexical blocking over that key and
the subject/predicate pair avoids comparing every fact with every other fact. Only cross-document
candidates are adjudicated. The adjudicator must choose:

- `corroborates`: materially the same claim after safe normalization;
- `contradicts`: the same subject, metric, period, scope, and modality with incompatible values;
- `reconciles`: a surface conflict explained by time, scope, unit, definition, or modality; or
- `unrelated`: not stored as a relationship.

### Required cases in the included demo

| Case | Sources | Result |
| --- | --- | --- |
| Corroboration | RBI Annual Report p. 8 and IMF Article IV p. 3 | Both report FY2024/25 real GDP growth of 6.5%. |
| Likely contradiction | RBI Annual Report p. 17 and IMF Article IV p. 3 | FY2025/26 forecasts differ: 6.5% versus 6.6%. |
| Reconciliation | Economic Survey p. 4 and RBI Annual Report p. 8 | 6.4% is the First Advance Estimate; 6.5% is the later Second Advance Estimate. |
| Failure | IMF Article IV p. 5 | Decimal values in a dense table split across lines, so the candidate is quarantined until layout-aware header binding is available. |

### Storage and incremental behavior

SQLite keeps documents, page text, accepted facts, relationships, and failure records. A SHA-256
content hash makes ingestion idempotent: adding the same PDF again does not rebuild its facts.
Relationships are appended for new cross-document candidates instead of rebuilding the layer.

### API

- `POST /api/uploads` - validate and enqueue new PDFs
- `GET /api/jobs/{id}` - processing status
- `GET /api/facts` - facts with evidence and context
- `GET /api/relations` - enriched relationship pairs
- `GET /api/documents/{id}/pages/{page}` - extracted page text
- `GET /api/documents/{id}/pages/{page}/image` - rendered source page
- `GET /api/failures` - quarantined extraction and reasoning failures

## Important Decisions and Trade-offs

- A compact FastAPI service and dependency-free browser interface give reviewers both an API and a
  polished inspection flow without a separate frontend build toolchain.
- SQLite is sufficient for this prototype and keeps the submission runnable. A graph database would
  add operations without improving discovery or grounding, which are the important parts here.
- Verbatim evidence validation is deterministic. Relationship labels remain probabilistic and carry
  confidence plus an explicit explanation.
- Page-level provenance is robust to printed page numbers that jump inside curated excerpts.
- API calls operate on bounded chunks, while content hashes and candidate blocking control repeat
  work and pairwise cost.

## Limitations and Next Steps

- Multi-column prose works well, but dense tables need layout-coordinate reconstruction. The demo's
  failure case shows why row text alone is unsafe.
- Scanned PDFs need OCR before the current text path can process them.
- Semantic candidate blocking currently combines model-generated keys with lexical similarity. At
  larger scale, I would add embeddings plus an approximate nearest-neighbor index.
- The background executor is intentionally single-process. Production would move jobs to a durable
  queue with retries, cancellation, and per-document progress.
- Dates and unit conversions are model-produced, then reviewed during relationship adjudication.
  A financial unit/date normalization test suite would reduce that remaining uncertainty.
- The prototype stores source PDFs locally. Production requires encrypted object storage, retention
  controls, tenant isolation, and deletion workflows.

## Additional Notes

The repository never stores API credentials. `OPENAI_API_KEY` is read from the local environment,
and responses are requested with storage disabled. The included JSON sample contains selected,
manually source-verified outputs, not hard-coded extraction logic; uploaded documents always travel
through the general pipeline.

AI tools used: Codex supported implementation and source inspection. The runtime uses the OpenAI
Responses API with strict JSON Schema outputs for extraction and relationship adjudication. All
accepted evidence still passes a deterministic page-level gate outside the model.
