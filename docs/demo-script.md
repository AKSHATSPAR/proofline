# Proofline demo script (target: 2:30-2:50)

## 0:00-0:25 - Frame the problem

Open the Relationships view.

“Proofline turns PDFs into atomic facts with page-level evidence, then tells a reviewer whether
sources agree, genuinely disagree, or only appear inconsistent. The checked-in demo uses three
India macroeconomy reports and works without credentials.”

## 0:25-0:55 - Process a PDF

Click **Add PDFs**. If recording with an API key, upload one starter PDF and show the background
progress. Otherwise explain that the precomputed sample follows the same pipeline and that new
uploads are enabled by setting `OPENAI_API_KEY`.

Mention content hashing, page-separated chunks, and the fail-closed evidence gate.

## 0:55-1:30 - Corroboration and evidence

Filter to **Corroborates**. Show RBI 6.5% beside IMF 6.5% for FY2024/25. Open one evidence drawer
and point to the rendered PDF page, page number, verbatim quote, scope, and confidence.

## 1:30-1:55 - Likely contradiction

Filter to **Contradicts**. Show the FY2025/26 real GDP forecasts: RBI 6.5% versus IMF 6.6%. Explain
that publication vintage contextualizes the disagreement but does not make the values equivalent.

## 1:55-2:20 - Contextual reconciliation

Filter to **Reconciles**. Show Economic Survey 6.4% versus RBI 6.5%. Point out that the first uses
the First Advance Estimate and the later report uses the Second Advance Estimate.

## 2:20-2:40 - Failure handling

Open **Diagnostics**. Show the IMF table value whose decimal was split across lines. Explain that
Proofline quarantined it instead of promoting an unsafe year-to-value mapping.

## 2:40-2:50 - Close

Open **Facts** briefly, then mention the FastAPI docs and incremental SQLite layer.

“The next production step is layout-aware table reconstruction and OCR, but the core loop -
discover, ground, compare, and explain - is working end to end.”
