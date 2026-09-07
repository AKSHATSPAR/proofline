# Design benchmark: what Proofline borrows, and what it deliberately does not

Research date: 2026-09-07. This is a design comparison, not a claim that Proofline reproduces a
commercial system. Only public product material, documentation, and source repositories were used.

| Reference | Publicly observable pattern | Decision in Proofline |
| --- | --- | --- |
| [Hebbia Matrix](https://www.hebbia.com/product) | A finance-oriented review workflow where answers remain tied to citations and analysts validate results. Its implementation is proprietary, so no private stack is inferred. | Treat evidence inspection as part of the core product flow, not a debug screen. |
| [LlamaExtract API](https://developers.api.llamaindex.ai/api/resources/extract/methods/get/) | Schema-defined extraction exposes source-citation and confidence controls, page targeting, and versioned configurations. | Keep strict schemas, per-fact confidence, and explicit page provenance while retaining a provider-independent adapter. |
| [Docling](https://github.com/docling-project/docling) | The open-source Python stack models document layout and provenance, with optional OCR and local model backends. | Borrow the bounding-box provenance principle using PyMuPDF now; defer the much larger parser/OCR stack until a failed document needs it. |
| [Microsoft GraphRAG default dataflow](https://github.com/microsoft/graphrag/blob/main/docs/index/default_dataflow.md) | Entities, relationships, and optional claims are first-class records linked back to source text units; claim extraction is presented as a task that needs tuning. | Store typed claims and relationships separately, preserve source links, and quarantine uncertain extraction rather than hiding it. |
| [ExtractBench](https://github.com/run-llama/ExtractBench) | Enterprise extraction is scored separately on value accuracy, page grounding, and word-level box grounding; failed documents score zero rather than disappearing. | Add a deterministic grounding audit and visible word-level highlights. Keep failures in an explicit ledger. |

## Why the stack was not replaced

Distinctiveness is useful only when it improves the result. Replacing FastAPI, SQLite, or PyMuPDF
with unfamiliar infrastructure would make this assignment harder to run without improving its core
risk: whether a banker can verify a derived claim. The current stack is intentionally compact:

- Python, FastAPI, Pydantic, and SQLite for typed extraction, API delivery, and durable local state;
- PyMuPDF for page-preserving text extraction, rendering, and coordinate recovery;
- Gemini's no-payment free tier by default, with an optional OpenAI adapter;
- dependency-free HTML, CSS, and JavaScript so reviewers can run one process with no frontend build.

The differentiated addition is therefore architectural rather than cosmetic: the LLM proposes a
quote and page, a deterministic gate accepts or rejects it, and a separate coordinate pass locates
the exact words for the reviewer. `GET /api/audits/grounding` measures both page-gate coverage and
word-anchor coverage without spending API credits.

## Next upgrade threshold

Docling or a comparable layout/OCR adapter becomes worthwhile when evaluation failures cluster on
scans, merged table headers, or cross-page rows. Until that evidence exists, it remains an optional
parser behind the current page interface rather than a mandatory dependency. This keeps the common
path fast while making the planned upgrade concrete.
