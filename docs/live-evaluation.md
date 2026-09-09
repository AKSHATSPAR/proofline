# Held-out evaluation

The checked demo is useful for review, but it cannot show whether the upload pipeline handles an
unseen file. I therefore ran documents from the starter dataset through the same ingestion path used
by the interface. No facts were added by hand to these runs.

## Complete presentation run

Input: the full 27-page Delhivery Q4 FY24 earnings presentation.

The first strict run exposed a layout problem. The model found valid values, but ordinary PDF text
often separated a table value from its row and column headers. The pipeline correctly rejected those
candidates because their structured fields were not fully supported.

I then added a separate, bounded row-and-column view from PyMuPDF for interpreting ruled tables. The
ordinary page text remains the only acceptable source for evidence quotes. I also allowed unsupported
optional scope, period, date, or normalization fields to be removed before one complete revalidation.
The subject, metric, object, reported number, unit, comparison key, and quote are never rewritten.

The resulting run produced:

- 29 accepted facts from the FY24 summary, Q4 FY24 summary, and operating metrics pages;
- 29 of 29 facts passing page grounding and structured field validation;
- 29 of 29 facts located at word level in the original PDF; and
- no unsupported candidate promoted to the fact register.

I rendered and checked the three source slides manually. The accepted values match the visible FY24
and Q4 FY24 figures.

## Multi-document and recovery run

I also ran the Delhivery prospectus, annual report, and earnings presentation as one incremental set.
The request plan used page-labelled chunks followed by batched relationship comparison.

The persisted result contained 45 accepted facts from the completed prospectus and annual-report
work, all of which passed page anchoring, structured field validation, and word anchoring. Another
164 candidates were quarantined. One cross-document relationship was accepted: automated sort
capacity increased from 3.70 million shipments per day on 31 December 2021 to 7.1 million on
31 March 2024. The different dates explain why both values can be true, so the relationship was
classified as a reconciliation and passed the deterministic relationship checks.

This run also exercised recovery. A line break between a minus sign and `44,501.15` exposed a numeric
normalization bug. After the parser and regression test were fixed, the next run reused completed
chunks and resumed from the failure. Provider quota and temporary capacity errors were retained as
diagnostics and received only bounded retries.

## What this establishes

These runs cover a complete unseen presentation, a multi-document incremental pass, exact evidence
anchoring, layout-assisted table interpretation, quarantined failures, resumability, and one held-out
relationship. They do not constitute a statistically meaningful accuracy benchmark. A larger
labelled relationship set is still needed to measure retrieval recall and relationship precision.

Borderless tables, merged headers, tables that continue across pages, and scanned PDFs remain the
main document-processing gaps. Those cases should be improved with measured parser or OCR changes,
not by weakening the evidence gate.
