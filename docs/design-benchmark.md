# What I learned from similar systems

Research date: 2026-09-07. Once the core pipeline worked, I looked at products and open-source
projects that solve nearby problems. I wanted to find useful ideas, not copy a product. I only used
public product pages, documentation, and source repositories.

| Reference | What caught my attention | What I did with it |
| --- | --- | --- |
| [Hebbia Matrix](https://www.hebbia.com/product) | Citations stay inside the finance review workflow, where an analyst can check the answer. The implementation is private, so I did not make assumptions about its stack. | I made evidence inspection part of the main review flow instead of hiding it on a debug page. |
| [LlamaExtract API](https://developers.api.llamaindex.ai/api/resources/extract/methods/get/) | Its public API includes schemas, source citations, confidence controls, target pages, and versioned configurations. | Proofline keeps a strict schema, confidence on every fact, and the source page, while keeping the model provider replaceable. |
| [Docling](https://github.com/docling-project/docling) | It treats layout and provenance as real document data. It can also add OCR and local models when needed. | I borrowed the bounding-box idea using PyMuPDF. I did not add the much larger parsing stack before the failures justified it. |
| [Microsoft GraphRAG default dataflow](https://github.com/microsoft/graphrag/blob/main/docs/index/default_dataflow.md) | Claims and relationships are stored separately and linked back to source text. Its docs also warn that claim extraction needs tuning. | Proofline stores facts and relationships separately, keeps source links, and records uncertain work as a failure. |
| [ExtractBench](https://github.com/run-llama/ExtractBench) | It measures value accuracy, page grounding, and word-level grounding separately. Failed documents still count against the result. | I added a local grounding audit, visible word highlights, and a failure ledger. |

## Why I kept the stack small

I decided against changing frameworks just to make the project look different. The main risk is not
whether the database is fashionable. It is whether someone can verify a fact before using it. The
stack stays small for that reason:

- Python, FastAPI, Pydantic, and SQLite for typed extraction, API delivery, and durable local state;
- PyMuPDF for page-preserving text extraction, rendering, and coordinate recovery;
- Gemini's no-payment free tier by default, with an optional OpenAI adapter;
- dependency-free HTML, CSS, and JavaScript so reviewers can run one process with no frontend build.

The part I chose to push further was evidence. The model proposes a quote and page. Regular Python
code accepts or rejects that quote, then a separate coordinate pass finds the exact words for the
reviewer. `GET /api/audits/grounding` measures page and word coverage without using API credits.

## When I would add a larger parser

I would add Docling, or a similar layout and OCR adapter, when tests show repeated failures on scans,
merged headers, or tables that continue across pages. Until then, it can sit behind the current page
interface as an optional parser. The common case stays easy to run, and there is still a clear path
for harder documents.
