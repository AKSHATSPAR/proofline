# Live model evaluation

I did not want the hand-checked demo to be the only proof that the pipeline worked. I also ran an
unseen starter document through the same code used by the upload screen.

## Run

- Date: 2026-09-07
- Provider/model: Gemini free tier, `gemini-3.7-flash`
- Input: the complete 27-page Delhivery Q4 FY24 earnings presentation from the starter dataset
- Processing: two page-labelled text chunks through the same general ingestion path used by the UI

## Baseline result

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

## Stricter field-grounding rerun

On 2026-09-08 I added a second gate that checks whether structured fields are supported by the
accepted quote. The first completed rerun produced:

- 7 facts accepted;
- 17 candidates quarantined with field-level reasons; and
- 0 unsupported candidates promoted to facts.

The retained facts cover FY24 and Q4 FY24 revenue, shipments, reported EBITDA, and adjusted EBITDA.
Most quarantined candidates copied a valid sentence but attached a date, period, or unit that was
only visible in a distant table header. That result is lower recall than the baseline, but it is a
more honest boundary for page-text extraction. The application now shows both quote grounding and
structured field coverage in its audit panel.

Later reruns hit the provider's free-tier quota for both chunks. After the complete bounded retry
budget, Proofline stored the errors and marked the document `failed`. Those quota-blocked attempts
are not counted as extraction evaluations.

## What broke and what I changed

An earlier attempt with `gemini-3.8-flash` hit one temporary capacity error and one quota error. The
errors were visible, but retrying the run was clumsy. I made these changes:

- defaults to the stable `gemini-3.7-flash` free model;
- retries 429 and transient 5xx responses with bounded backoff;
- marks all-failed and partially processed documents as `failed` or `partial`;
- marks a successful call with no candidates as `empty`, with a reviewable diagnostic; and
- allows those documents to be submitted again instead of treating them as complete.

The run found one smaller bug too. Duplicate candidates in a response made the displayed insert
count one higher than the number of facts in SQLite. The count now increases only when a new row is
actually stored.

## One number I would not trust yet

The model gave every accepted candidate a confidence of `1.0`. The evidence still passed an
independent check, but that confidence is clearly not a calibrated probability. The interface now
uses high, medium, and low review signals instead of percentages. A labelled extraction set is still
needed before treating the underlying value as calibrated.

## Focused cross-document follow-up

On 2026-09-08 I prepared a second held-out check using one FY24 financial-performance page from the
Delhivery annual report and one FY24 summary page from its earnings presentation. The pages express
the same revenue at different precision and scale: ₹81,415.38 million and ₹8,142 crore.

The free provider quota returned a 429 response for both pages after the bounded retry budget, so no
facts or relationships from this attempt are counted as evaluation results. I did not switch on
billing or substitute hand-written outputs. The source pair did expose a deterministic edge case,
which now has a regression test: compatible numbers are compared in base units while respecting the
coarser source's stated rounding precision. A future quota window can rerun the same two-page check.

## Resumable full-set attempt

On 2026-09-08 I also ran all three Delhivery PDFs after increasing the safe chunk size and batching
relationship candidates. The planned request budget was 18 extraction requests, followed by one
relationship request.

The first pass found a normalizer defect in a real annual-report fragment: the PDF placed a line
break between a minus sign and `44,501.15`. The validator removed ordinary spaces around signs but
not newline characters, so numeric parsing raised an exception. The completed first chunk remained
in SQLite. After fixing the parser and adding a regression test, the rerun resumed at the failed
chunk rather than restarting the document.

The configured free-tier key had already used part of its daily allowance before this run. It
reached that allowance during the annual report, so the final state was:

- 16 accepted facts from the complete prospectus;
- 24 accepted facts from completed annual-report chunks;
- 40 of 40 accepted facts passed page grounding, structured field validation, and word anchoring;
- 76 candidates were quarantined by evidence or field validation;
- seven annual-report chunks and the earnings presentation remained retryable; and
- the one remaining relationship batch received a quota response, so no relationship result from
  this attempt is counted.

This is evidence that chunk-level recovery works on the real starter data. It is not a completed
three-document relationship benchmark, and I have kept that limitation explicit.
