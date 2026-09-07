# Live model evaluation

## Run

- Date: 2026-09-07
- Provider/model: Gemini free tier, `gemini-3.7-flash`
- Input: the complete 27-page Delhivery Q4 FY24 earnings presentation from the starter dataset
- Processing: two page-labelled text chunks through the same general ingestion path used by the UI

## Result

- 24 unique facts accepted into SQLite
- 1 candidate rejected because its quote could not be anchored verbatim to the claimed PDF page
- 0 ungrounded candidates promoted to facts

The accepted facts included FY24 and Q4 FY24 revenue, reported and adjusted EBITDA, parcel volume,
PTL tonnage, active customers, profit after tax, balance-sheet metrics, operating cash flow, capex,
and ESOP participation.

## Verification

Every accepted quote passed the deterministic page-level evidence check. In addition, PDF pages 6,
8, 17, 20, 22, and 23 were rendered and visually inspected. The model's table-column mappings for
FY24/Q4 FY24, dates, units, and signs matched the rendered source on those sampled pages.

After adding coordinate-level provenance, the local grounding audit was run over the same database:
24/24 accepted facts still passed the page gate, and 24/24 were located at word level in the
original PDF. This audit uses PDF text coordinates and makes no model calls.

The rejected candidate came from a multi-column working-capital table whose extracted reading order
did not preserve a verbatim row. Quarantining it was the correct fail-closed outcome.

## What the run changed

An earlier attempt with `gemini-3.8-flash` returned one temporary high-demand error and one quota
error. Those failures were stored rather than silently swallowed, but they exposed two resilience
gaps. The implementation now:

- defaults to the stable `gemini-3.7-flash` free model;
- retries 429 and transient 5xx responses with bounded backoff;
- marks all-failed and partially processed documents as `failed` or `partial`; and
- allows those documents to be submitted again instead of treating them as complete.

The run also revealed that duplicate candidates inside one response made the reported insert count
one higher than the number of unique stored facts. Insert counts now reflect only rows actually
added to SQLite.

## Remaining observation

The model assigned confidence `1.0` to every accepted candidate. Grounding is independently checked,
but the model confidence is therefore not well calibrated and should not be interpreted as a formal
probability. A future evaluation set should calibrate confidence against labelled extraction errors.
