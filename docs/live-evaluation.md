# Live model evaluation

I did not want the hand-checked demo to be the only proof that the pipeline worked. I also ran an
unseen starter document through the same code used by the upload screen.

## Run

- Date: 2026-09-07
- Provider/model: Gemini free tier, `gemini-3.7-flash`
- Input: the complete 27-page Delhivery Q4 FY24 earnings presentation from the starter dataset
- Processing: two page-labelled text chunks through the same general ingestion path used by the UI

## Result

- 24 unique facts accepted into SQLite
- 1 candidate rejected because its quote could not be anchored verbatim to the claimed PDF page
- 0 ungrounded candidates promoted to facts

The accepted set covered FY24 and Q4 FY24 revenue, reported and adjusted EBITDA, parcel volume, PTL
tonnage, active customers, profit after tax, balance-sheet metrics, operating cash flow, capex, and
ESOP participation.

## Verification

All 24 accepted quotes passed the page check. I also rendered pages 6, 8, 17, 20, 22, and 23 and
checked them myself. On those pages, the model matched the right FY24 or Q4 FY24 column and kept the
dates, units, and negative signs intact.

I then ran the local grounding audit over the same database. All 24 facts still passed the page
check, and all 24 could be located at word level in the original PDF. This audit uses PDF text
coordinates and makes no model calls.

The rejected candidate came from a multi-column working-capital table. Text extraction did not keep
the row together, so Proofline could not find the proposed quote on the page. It left the candidate
in Diagnostics instead of accepting it.

## What broke and what I changed

An earlier attempt with `gemini-3.8-flash` hit one temporary capacity error and one quota error. The
errors were visible, but retrying the run was clumsy. I made four changes:

- defaults to the stable `gemini-3.7-flash` free model;
- retries 429 and transient 5xx responses with bounded backoff;
- marks all-failed and partially processed documents as `failed` or `partial`; and
- allows those documents to be submitted again instead of treating them as complete.

The run found one smaller bug too. Duplicate candidates in a response made the displayed insert
count one higher than the number of facts in SQLite. The count now increases only when a new row is
actually stored.

## One number I would not trust yet

The model gave every accepted candidate a confidence of `1.0`. The evidence still passed an
independent check, but that confidence is clearly not a calibrated probability. I would need a
labelled extraction set before presenting model confidence as anything more than a ranking signal.
