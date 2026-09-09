# Proofline demo script (target: 2:40 to 2:55)

Use a screen recording with voice narration.

## 0:00 to 0:18 | Introduction

Show the Comparisons page.

“Hi, this is Proofline. I built it to compare claims across financial PDFs while keeping every
result tied to the exact page and words that support it. I will show how it handles agreement,
conflict, reconciliation, and a failed extraction, then briefly show the API and repository.”

## 0:18 to 0:38 | Documents and pipeline

Open Documents, then return to Comparisons.

“This demonstration uses excerpts from three public reports on the Indian economy. Pages remain
separate during extraction. Repeat uploads are skipped, and interrupted runs continue from their
unfinished chunks. If a quote cannot be verified on its claimed page, the fact is rejected.”

## 0:38 to 1:08 | Corroboration

Filter to Corroborates and open the evidence for the 6.5% FY2024/25 result.

“The RBI and IMF both report real GDP growth of 6.5% for the same period. The evidence drawer shows
the source, page, quote, and highlighted words on the original PDF. The highlight is found only after
the quote and structured fields pass deterministic checks.”

## 1:08 to 1:32 | Contradiction

Filter to Contradicts.

“For FY2025/26, the RBI forecast is 6.5% and the IMF forecast is 6.6%. These claims refer to the same
metric and period but give different values, so Proofline marks a likely contradiction and keeps both
sources available for review.”

## 1:32 to 1:56 | Reconciliation

Filter to Reconciles.

“Here, 6.4% and 6.5% look inconsistent at first. The Economic Survey uses the First Advance Estimate,
while the later RBI report uses the Second Advance Estimate. Proofline therefore explains this as a
revision, not a direct contradiction.”

## 1:56 to 2:16 | Failure

Open Needs review and select the borderless-table failure.

“This table split a decimal value across lines, so the year-to-value mapping was ambiguous. Proofline
does not present the value as reliable. It shows the issue here so a person can review it.”

## 2:16 to 2:34 | Fact register

Open Facts and one evidence drawer.

“The Facts page keeps each claim beside its period and source. Opening one takes me back to the exact
quote and original PDF page instead of showing only a summary.”

## 2:34 to 2:48 | API and implementation

Open `/docs`, then briefly show the repository tree on GitHub.

“The browser interface and API use the same FastAPI service and SQLite store. The API covers uploads,
job status, facts, relationships, review issues, and source pages. The repository also
includes tests, deployment configuration, and the evaluation notes.”

## 2:48 to 2:55 | Close

Return to Comparisons.

“The main remaining gaps are scanned PDFs and unusually structured tables. For supported documents,
the full loop works from extraction and evidence checking to comparison and source review.”
