# Proofline demo script (target: 2:30-2:50)

## 0:00-0:25 - Frame the problem

Open the Relationships view.

“I built Proofline to answer a simple question: when two documents say something about the same
topic, do they agree? It pulls out facts, keeps the source page attached, and explains real and
apparent conflicts. This example uses three reports on the Indian economy.”

## 0:25-0:55 - Process a PDF

Click **Add PDFs**, upload the earnings presentation, and show the background progress. Explain that
the included example can still be reviewed without a key, while new uploads use a free-tier
`GEMINI_API_KEY`.

Briefly mention that pages stay separate, repeat uploads are skipped by file hash, and a fact is
rejected if its quote cannot be found on the claimed page.

## 0:55-1:30 - Corroboration and evidence

Filter to **Corroborates**. Show RBI 6.5% beside IMF 6.5% for FY2024/25. Open one evidence drawer
and point to the highlighted words, page number, quote, scope, and confidence. Say that regular code
finds this highlight after the quote passes the evidence check. The model does not invent the box.

## 1:30-1:55 - Likely contradiction

Filter to **Contradicts**. Show the FY2025/26 real GDP forecasts: RBI says 6.5%, while the IMF says
6.6%. They are forecasts published at different times, but they still make different claims about
the same metric and period.

## 1:55-2:20 - Contextual reconciliation

Filter to **Reconciles**. Show the Economic Survey's 6.4% beside the RBI's 6.5%. The first number is
the First Advance Estimate. The later RBI report uses the Second Advance Estimate, so this is a
revision rather than a direct contradiction.

## 2:20-2:40 - Failure handling

Open **Diagnostics**. Show the IMF table value whose decimal was split across lines. Proofline could
not safely tell which year owned the value, so it kept the candidate out of the fact table.

## 2:40-2:50 - Close

Open **Facts** briefly, then point out the FastAPI docs and the local SQLite database.

“The main gap is dense tables and scanned PDFs. For the documents it can read, the full loop is
working: discover a fact, check its evidence, compare it with other sources, and explain the result.”
