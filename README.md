# Proofline

Proofline answers a practical question: when several PDFs talk about the same subject, do they
agree? It pulls out individual facts, keeps the source page beside each one, and explains whether
two claims support each other, conflict, or differ for a valid reason such as time or scope.

The app opens with an India macroeconomy example that I checked against the original PDFs. You can
explore that example without an API key. To process new files, the default setup uses Gemini's free
API tier. OpenAI is also supported if you already use it.

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
# Create a free key at https://aistudio.google.com/app/apikey,
# add it as GEMINI_API_KEY in .env, then restart the server.
uv run proofline-serve
```

Keep the Google AI Studio project on the **Free Tier** and do not select **Set up billing**. The
default model is `gemini-3.7-flash`. Google states that free-tier prompts and responses may be used
to improve its products, so use the included public starter documents, not confidential material.

To use OpenAI instead, set `PROOFLINE_PROVIDER=openai` and `OPENAI_API_KEY` in `.env`. Provider keys
stay server-side and are never sent to the browser.

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

### Public demo deployment

The repository includes a Render Blueprint. Connect the GitHub repository from Render's Blueprint
screen and choose the free service defined in `render.yaml`. No secret is required. The deployed app
starts from a fresh SQLite database and loads the checked demonstration automatically.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/AKSHATSPAR/proofline)

The public deployment is deliberately read-only. This keeps a shared provider key from being used
by strangers while preserving the complete review experience, including the original public report
excerpts and highlighted evidence pages. New PDF processing remains available through the local
setup above.

Render's free service can sleep after 15 minutes without traffic, so the first visit may take about
a minute to wake up. Its filesystem is temporary, which is acceptable here because the public demo
rebuilds from bundled data at startup.

I recorded the latest real-model test in [`docs/live-evaluation.md`](docs/live-evaluation.md). Notes
from studying similar products and open-source projects are in
[`docs/design-benchmark.md`](docs/design-benchmark.md).

## Video Demo

The final video link will go here after recording. I have kept the walkthrough under three minutes;
the outline is in [`docs/demo-script.md`](docs/demo-script.md).

## Approach

### Pipeline

```text
PDF upload
   -> content hash / incremental skip
   -> page-separated PyMuPDF extraction
   -> page-labelled, bounded chunks
   -> structured fact discovery
   -> verbatim evidence gate
   -> deterministic field validation
   -> word-level source anchoring
   -> SQLite fact register
   -> indexed semantic candidate retrieval
   -> context-aware relationship adjudication
   -> deterministic relationship guardrails
   -> API and review UI
```

I did not want to lock the project to a small list of financial metrics. Each fact stores a subject,
predicate, typed value, original and normalized units, date or period, scope, modality, confidence,
comparison key, and a short source quote. This lets a new kind of fact appear without requiring a
database migration.

### Grounding before reasoning

My main rule is that a fact should not enter the knowledge layer unless its evidence can be found on
the claimed PDF page. The model must return a verbatim quote and a one-based page number. Proofline
normalizes whitespace and checks the quote against the text from that page. It then checks that the
stored number, unit, period, date, modality, and any unit conversion agree with the quote. A failed
check goes to Diagnostics with the rejected candidate and field-level reasons.

For facts that pass, Proofline finds the quote's coordinates and highlights the words in the source
page. A small word-sequence fallback handles PDF quirks such as superscript footnote numbers. This
may miss a few valid facts, but I prefer a visible omission to a claim that cannot be checked.

### Cross-document comparison

Comparing every fact with every other fact quickly becomes wasteful. Proofline builds an inverted
index over normalized metric terms and retrieves only cross-document facts with compatible entity
and metric signatures. A small alias set handles common variants such as turnover versus revenue
and profit after tax versus net profit. This avoids a full all-pairs scan while keeping the required
demo matches. The comparison step receives each fact plus a bounded window from its source page,
then chooses one of four results:

- `corroborates`: materially the same claim after safe normalization;
- `contradicts`: the same subject, metric, period, scope, and modality with incompatible values;
- `reconciles`: a surface conflict explained by time, scope, unit, definition, or modality; or
- `unrelated`: not stored as a relationship.

Before a relationship is stored, deterministic guardrails reject impossible numeric labels. For
example, two equal values cannot be called a contradiction, and different normalized values cannot
be called corroboration.

### Required cases in the included demo

| Case | Sources | Result |
| --- | --- | --- |
| Corroboration | RBI Annual Report p. 8 and IMF Article IV p. 3 | Both report FY2024/25 real GDP growth of 6.5%. |
| Likely contradiction | RBI Annual Report p. 17 and IMF Article IV p. 3 | FY2025/26 forecasts differ: 6.5% versus 6.6%. |
| Reconciliation | Economic Survey p. 4 and RBI Annual Report p. 8 | 6.4% is the First Advance Estimate; 6.5% is the later Second Advance Estimate. |
| Failure | IMF Article IV p. 5 | Decimal values in a dense table split across lines, so the candidate is quarantined until layout-aware header binding is available. |

### Storage and incremental behavior

SQLite stores the documents, extracted page text, accepted facts, relationships, and failures. A
SHA-256 hash identifies each source file. Uploading the same PDF twice does not process it twice, and
new documents add relationships without rebuilding the existing layer.

### API

- `POST /api/uploads` - validate and enqueue new PDFs
- `GET /api/jobs/{id}` - processing status
- `GET /api/facts` - facts with evidence and context
- `GET /api/relations` - enriched relationship pairs
- `GET /api/documents/{id}/pages/{page}` - extracted page text
- `GET /api/documents/{id}/pages/{page}/image` - rendered source page
- `GET /api/facts/{id}/evidence-image` - source page with the fact's exact evidence highlighted
- `GET /api/audits/grounding` - deterministic page- and word-anchor coverage
- `GET /api/failures` - quarantined extraction and reasoning failures

## Important Decisions and Trade-offs

- I used one FastAPI process and a small browser interface so the reviewer gets both an API and a
  useful inspection screen without setting up a separate frontend project.
- SQLite is enough for this prototype. A graph database would add setup work, but it would not make
  fact discovery or source checking more reliable.
- Evidence and structured field matching are deterministic. Relationship labels still use a model,
  so every label carries a qualitative review signal and a short explanation. Raw confidence is
  retained in the API for sorting, not presented as a calibrated probability.
- Highlights are created from the original PDF when the reviewer opens a fact. They are not citation
  coordinates invented by the model.
- I use the PDF's actual page index because printed page numbers can jump inside curated excerpts.
- Bounded chunks keep model requests manageable. File hashes prevent duplicate extraction, and
  candidate filtering limits the number of fact pairs sent for comparison.
- Gemini is the default because its free tier makes the project easier to try. The OpenAI adapter is
  there for people who already have API billing.
- Temporary provider errors are retried with bounded backoff, including the error type returned by
  the provider's newer interactions endpoint. A document can be marked `partial`, `empty`,
  `rejected`, or `failed`, and it can be submitted again after the provider recovers. The UI and CLI
  surface that status instead of presenting zero extracted facts as a successful run.

## Limitations and Next Steps

- Dense tables are the clearest weak spot. Multi-column prose usually works, but plain extracted text
  can lose the connection between a table header and its value. The demo keeps one such failure in
  Diagnostics instead of guessing.
- Scanned PDFs need an OCR step before Proofline can read them.
- The metric alias set is intentionally small. A larger collection would need a measured vocabulary
  expansion or a hybrid semantic index, with recall checked against labelled cross-document pairs.
- Jobs run in one background process. A production version would need a durable queue, cancellation,
  retries, and saved progress for each chunk.
- The deterministic validator checks common numeric scales, currencies, dates, fiscal years, and
  fiscal quarters. Unusual accounting units and non-standard periods still need broader test data.
- The public demonstration bundles only its three public institutional excerpts. Locally uploaded
  PDFs stay on that machine. A real multi-tenant service would need encrypted object storage,
  retention settings, tenant isolation, and deletion workflows.

## Additional Notes

API keys are read from the local environment and are never stored in the repository. OpenAI requests
also disable response storage. The included JSON file contains a small set of outputs that I checked
against the source PDFs. It is sample data for the no-key demo, not special-case extraction logic.
Every uploaded PDF still goes through the same general pipeline.

I used Codex throughout implementation to inspect the source material, discuss design choices, write
and review code, and test the browser flow. Gemini is the runtime model used for extraction and fact
comparison. Both model adapters request schema-constrained JSON, but the final evidence check runs in
ordinary Python code outside the model.
