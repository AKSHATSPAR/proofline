# Proofline demo script (target: 2:45 to 2:55)

Record the screen with microphone narration. A camera is not required.

Before recording, keep these ready:

- the local app at `http://127.0.0.1:8000`;
- `output/video-demo-delhivery-page-8.pdf` in the file picker;
- the API page at `http://127.0.0.1:8000/docs`;
- the GitHub repository; and
- the deployed app at `https://proofline-y1ln.onrender.com`.

If document processing waits for the free service, pause the recording after the progress indicator
appears and resume when it completes. Do not spend the three-minute limit showing an idle screen.

## 0:00 to 0:14 | Introduction

Show the local Comparisons page.

“Hi, this is Proofline. It compares facts across financial PDFs while keeping every result linked to
its source page. I will process a real PDF, then show agreement, contradiction, reconciliation, and
a result requiring review.”

## 0:14 to 0:40 | Process a real PDF

Click **Use your PDFs**, select `video-demo-delhivery-page-8.pdf`, and click **Process PDFs**.

“This is an original page from the supplied Delhivery presentation. I am using one page to keep the
recording short, but the same pipeline was tested on the complete 27-page document. A result is
accepted only when its quote and important fields match the source.”

## 0:40 to 0:56 | Inspect the result

Open **Documents**, then **Facts**, and select one result from the uploaded PDF.

“The document now appears in the source list. Each fact includes its value, period, document, and PDF
page. Opening one shows the supporting quote and highlights it on the original page.”

## 0:56 to 1:19 | Corroboration

Open **Comparisons**, select **Corroborates**, and open one source page briefly.

“The RBI and IMF both report India’s real GDP growth as 6.5 percent for the same financial year.
Their wording differs, but the metric, period, and value match. Both source quotes and pages remain
available for verification.”

## 1:19 to 1:41 | Contradiction

Select **Contradicts** and show both values and quotes.

“Both reports forecast the same metric and period, but the RBI reports 6.5 percent while the IMF
reports 6.6 percent. Because the values differ, this is a likely contradiction.”

## 1:41 to 2:03 | Reconciliation

Select **Reconciles** and show the explanation and evidence.

“Context explains this difference. The Economic Survey uses the First Advance Estimate, while the
later RBI report uses the Second Advance Estimate. The change from 6.4 to 6.5 percent is therefore a
revision, not a direct contradiction.”

## 2:03 to 2:24 | Controlled failure

Open **Needs review** and show the table-layout issue.

“A borderless table split 456.1 across separate pieces of text, so it could not be matched reliably
to a year. Proofline does not present it as reliable. It preserves the attempted value, source text,
and next step for manual review.”

## 2:24 to 2:48 | Backend, repository, and deployment

Open `/docs`, briefly show the GitHub repository, and then open the deployed app.

“The interface and API share a FastAPI service and SQLite store. The API covers uploads, results, and
source pages. GitHub contains the implementation, tests, evaluation notes, and deployment setup. The
same version is available at this deployed link. It is read-only to protect the processing key, while
new PDFs can be processed locally.”

## 2:48 to 2:56 | Close

Return to the Comparisons page.

“That is the workflow from a real PDF to grounded facts, source review, cross-document comparison,
and transparent handling of uncertainty.”
