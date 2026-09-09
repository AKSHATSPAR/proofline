# Proofline

Proofline answers a practical question: when several PDFs talk about the same subject, do they
agree? It pulls out individual facts, keeps the source page beside each one, and explains whether
two claims support each other, conflict, or differ for a valid reason such as time or scope.

The app opens with an India macroeconomy example checked against the original PDFs. It can be
reviewed without an API key.

**Live demo:** [proofline-y1ln.onrender.com](https://proofline-y1ln.onrender.com)

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
default model is `gemini-3.7-flash`. Use only non-confidential documents with the free tier.

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

The same checks, plus a package build, run through GitHub Actions.

### Public demo deployment

The [live demo](https://proofline-y1ln.onrender.com) is read-only so no shared provider key is
exposed. It still includes the complete review workflow, original public report excerpts, and
highlighted evidence. Uploading new PDFs is available in the local setup. The free service may need
about a minute to wake after inactivity.

I recorded the latest real-model test in [`docs/live-evaluation.md`](docs/live-evaluation.md). Notes
from studying similar products and open-source projects are in
[`docs/design-benchmark.md`](docs/design-benchmark.md).

## Video Demo

The demo video link will be added after recording. The planned walkthrough is in
[`docs/demo-script.md`](docs/demo-script.md).

## Approach

### Pipeline

```text
PDF upload
   -> content hash / incremental skip
   -> page-separated text and layout-aware table extraction
   -> page-labelled, bounded chunks
   -> structured fact discovery
   -> verbatim evidence gate
   -> bounded repair of unsupported optional fields
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
normalizes whitespace and checks the quote against the text from that page. It then checks the
subject, metric, object, scope, comparison key, number, unit, period, date, modality, and any unit
conversion against the quote, a bounded window around it, and the document identity. A failed check
appears under Needs review with the rejected candidate and field-level reasons.

For facts that pass, Proofline finds the quote's coordinates and highlights the words in the source
page. A small word-sequence fallback handles PDF quirks such as superscript footnote numbers. This
may miss a few valid facts, but I prefer a visible omission to a claim that cannot be checked.

Ruled tables also get a bounded row-and-column view from PyMuPDF's table detector. That view helps
associate values with headers, but it is interpretation context only. A generated table row cannot
pass as evidence unless the quoted words are also present in the ordinary page text.

The extraction step sometimes finds a valid core claim but adds unsupported optional scope, date,
period, or unit conversion. Proofline removes only that optional metadata and runs the complete
validator again. It never rewrites the subject, metric, object, reported number, unit, comparison
key, or quote. Every repair is stored in the extraction note and shown in the evidence drawer.

### Cross-document comparison

Comparing every fact with every other fact quickly becomes wasteful. Proofline builds an inverted
index over normalized metric terms and retrieves only cross-document facts with compatible entity
and metric signatures. A small alias set handles common variants such as turnover versus revenue
and profit after tax versus net profit. This avoids a full all-pairs scan while keeping the required
demo matches. Plausible pairs are sent together in one schema-constrained comparison request. Each
pair keeps its own index and bounded source windows, so the response can still be checked one pair
at a time. The comparison step chooses one of four results:

- `corroborates`: materially the same claim after safe normalization;
- `contradicts`: the same subject, metric, period, scope, and modality with incompatible values;
- `reconciles`: a surface conflict explained by time, scope, unit, definition, or modality; or
- `unrelated`: not stored as a relationship.

Before a relationship is stored, deterministic guardrails reject impossible numeric labels. For
example, two equal values cannot be called a contradiction, and different comparable values cannot
be called corroboration. The comparison works with normalized values when supplied and safely falls
back to compatible raw units. It also respects the precision shown by each source, so a value rounded
to crore can agree with a more precise value in million without making 6.5% equal to 6.6%. Numerical
corroboration or contradiction also requires an explicit matching period or date. Two missing dates
are treated as unknown, not as a match.

### Demonstrated outcomes

| Case | Sources | Result |
| --- | --- | --- |
| Corroboration | RBI Annual Report p. 8 and IMF Article IV p. 3 | Both report FY2024/25 real GDP growth of 6.5%. |
| Likely contradiction | RBI Annual Report p. 17 and IMF Article IV p. 3 | FY2025/26 forecasts differ: 6.5% versus 6.6%. |
| Reconciliation | Economic Survey p. 4 and RBI Annual Report p. 8 | 6.4% is the First Advance Estimate; 6.5% is the later Second Advance Estimate. |
| Failure | IMF Article IV p. 5 | A borderless table split decimal values across lines, so the year-to-value match is ambiguous and the result remains under Needs review. |

### Storage and incremental behavior

SQLite stores the documents, extracted page text, accepted facts, relationships, and failures. A
SHA-256 hash identifies each source file. Uploading the same PDF twice does not process it twice, and
new documents add relationships without rebuilding the existing layer. Stored relationships and
completed `unrelated` decisions are excluded before candidate limits are applied, which keeps older
pairs from crowding out newly uploaded documents or being compared repeatedly. Each source chunk
also has a versioned completion record. If a provider fails halfway through a document, the next run
keeps completed chunks and retries only unfinished ones.

### API

The interactive `/docs` page covers PDF upload and job status, accepted facts and relationships,
rejected extraction records, extracted pages, evidence images, and the grounding audit.

## Important Decisions and Trade-offs

- One FastAPI process serves the API and browser interface, giving the reviewer one setup path.
- SQLite is sufficient for this prototype. A graph database would add setup cost without improving
  extraction or evidence quality.
- Evidence and field matching are deterministic. Relationship labels use a model and include an
  explanation. Raw confidence remains available through the API, while the interface focuses on
  inspectable source evidence instead of presenting it as a calibrated probability.
- Evidence highlights come from words on the original PDF page. They are not generated coordinates.
- Bounded chunks control request size. File hashes prevent duplicate extraction, chunk checkpoints
  make interrupted runs resumable, and temporary provider errors receive bounded retries. Partial,
  empty, rejected, and failed states remain visible instead of appearing as successful empty runs.

## Limitations and Next Steps

- Borderless or multi-page tables and merged headers can still lose the connection between a label
  and its value. The demo keeps one such failure under Needs review instead of guessing. Scanned PDFs
  also need OCR before they can be read.
- The metric alias set is intentionally small. A larger vocabulary or hybrid semantic index should
  be measured against labelled pairs before adoption.
- Jobs run in one process. Production use would need a durable queue, cancellation, and coordination
  across workers, although chunk progress already survives retries.
- Unusual accounting units and non-standard periods need broader validation data. The held-out
  Delhivery presentation produced 29 grounded facts, but a larger labelled relationship set is
  needed to measure retrieval recall and relationship precision.
- The public demo uses bundled public excerpts. A multi-tenant deployment would need encrypted
  object storage, retention controls, tenant isolation, and deletion workflows.

## Additional Notes

### Manual ownership and verification

I made the final product and engineering decisions, including the evidence-first reliability
boundary, the visible failure states, the free deployment, and the complete review workflow.

I checked the demonstration facts, periods, explanations, and failure case against the original PDF
pages. I also inspected the held-out presentation, exercised the review flows on desktop and mobile,
ran the automated checks, and smoke-tested the deployed application. Unsupported results stayed out
of the accepted fact layer.

API keys come from the local environment and are not stored in the repository. The bundled JSON is
only the checked no-key demonstration; uploaded PDFs still use the general pipeline.

### Tool disclosure

I used Codex as a development assistant for implementation and review. Gemini is the runtime model
used for structured extraction and fact comparison. These outputs are not accepted as evidence on
their own. The final quote anchoring, field validation, relationship guardrails, and audit run in
ordinary Python code and remain independently inspectable.
