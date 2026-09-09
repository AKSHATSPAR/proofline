const state = {
  config: null,
  summary: null,
  documents: [],
  facts: [],
  relations: [],
  failures: [],
  relationFilter: "all",
  viewInitialized: false,
};

const byId = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = response.headers.get("content-type")?.includes("application/json")
    ? await response.json()
    : null;
  if (!response.ok) throw new Error(body?.detail || `Request failed (${response.status})`);
  return body;
}

function periodLabel(fact) {
  if (fact.as_of_date) return `As of ${fact.as_of_date}`;
  if (fact.period_start && fact.period_end) {
    const start = Number(fact.period_start.slice(0, 4));
    const end = Number(fact.period_end.slice(0, 4));
    if (end === start + 1 && fact.period_start.endsWith("04-01")) return `FY${start}/${String(end).slice(2)}`;
    return `${fact.period_start} to ${fact.period_end}`;
  }
  const scopedPeriod = fact.scope
    .map((item) => item.match(/\bQ[1-4]\s+FY\s?\d{2,4}\b|\bFY\s?\d{2,4}(?:[/-]\d{2,4})?\b/i)?.[0])
    .find(Boolean);
  if (scopedPeriod) return scopedPeriod;
  return "Period not explicit";
}

function shortName(name) {
  return String(name).replace(/^\d+-/, "").replace(/-excerpt\.pdf$/i, "").replace(/\.pdf$/i, "").replaceAll("-", " ");
}

function diagnosticValue(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value !== "object") return String(value);
  if (Array.isArray(value)) return value.map(diagnosticValue).filter(Boolean).join("; ");

  const claim = [value.subject, value.predicate, value.object_text].filter(Boolean).join(" · ");
  if (claim) return claim;
  return JSON.stringify(value);
}

function diagnosticIssues(details) {
  const issues = details.remaining_issues?.length ? details.remaining_issues : details.issues;
  if (!Array.isArray(issues)) return "";
  return issues.map((issue) => {
    if (typeof issue !== "object" || issue === null) return String(issue);
    return issue.message || [issue.code, issue.field].filter(Boolean).join(": ") || JSON.stringify(issue);
  }).join(" ");
}

function diagnosticRow(label, value) {
  const text = diagnosticValue(value);
  return text ? `<dt>${esc(label)}</dt><dd>${esc(text)}</dd>` : "";
}

function stageLabel(stage) {
  return {
    table_header_binding: "Table layout",
    page_extraction: "Unreadable page",
    extraction: "Processing error",
    empty_extraction: "No facts found",
    evidence_validation: "Source mismatch",
    fact_validation: "Unsupported details",
    relation_validation: "Comparison issue",
  }[stage] || "Review issue";
}

function visibleScope(fact) {
  const predicate = fact.predicate.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  return fact.scope.filter((item) => {
    const normalized = item.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    return normalized && !predicate.includes(normalized);
  });
}

function scopeNote(fact) {
  const scope = visibleScope(fact);
  return scope.length ? `<span class="td-sub">${esc(scope.join(" · "))}</span>` : "";
}

function normalizedValueNote(fact) {
  if (fact.normalized_value === null || fact.normalized_value === undefined) return "";
  const sourceUnit = String(fact.unit || "").toLowerCase().replaceAll("per cent", "percent");
  const normalizedUnit = String(fact.normalized_unit || "").toLowerCase().replaceAll("per cent", "percent");
  if (fact.value_number !== null && fact.value_number !== undefined
    && Number(fact.normalized_value) === Number(fact.value_number)
    && sourceUnit === normalizedUnit) return "";
  const normalized = `${fact.normalized_value} ${fact.normalized_unit || ""}`.trim();
  if (!normalized || normalized.toLowerCase() === String(fact.object_text).trim().toLowerCase()) return "";
  return `<span class="td-sub">Comparable value: ${esc(normalized)}</span>`;
}

function documentStatusLabel(status) {
  return {
    ready: "Ready",
    partial: "Needs review",
    empty: "No facts found",
    rejected: "Needs review",
    failed: "Processing failed",
  }[status] || "Processing";
}

function relationTitle(relation) {
  const labels = {
    corroborates: "Sources agree on",
    contradicts: "Sources report different values for",
    reconciles: "Context explains the difference in",
  };
  return `${labels[relation.relation_type]} ${relation.left.predicate}`;
}

function evidenceCard(fact, side) {
  return `
    <article class="evidence-card">
      <div class="evidence-label"><span>${esc(side)} · ${esc(shortName(fact.document_name))}</span><button data-evidence="${esc(fact.id)}">PDF p. ${fact.page_number} ↗</button></div>
      <div class="value">${esc(fact.object_text)}</div>
      <div class="period">${esc(periodLabel(fact))} · ${esc(fact.modality)}</div>
      <blockquote>“${esc(fact.evidence_quote)}”</blockquote>
    </article>`;
}

function renderRelationships() {
  const list = byId("relationshipList");
  const items = state.relations.filter((item) => state.relationFilter === "all" || item.relation_type === state.relationFilter);
  if (!items.length) {
    list.className = "relationship-list empty-state";
    list.textContent = "No relationships match this filter.";
    return;
  }
  list.className = "relationship-list";
  list.innerHTML = items.map((relation) => `
    <article class="relation-card">
      <div class="relation-summary">
        <span class="relation-kind ${esc(relation.relation_type)}">${esc(relation.relation_type)}</span>
        <div class="relation-copy">
          <h3>${esc(relationTitle(relation))}</h3>
          <p>${esc(relation.explanation)}</p>
          <div class="context-chips">${relation.decisive_context.map((item) => `<span class="chip">${esc(item)}</span>`).join("")}</div>
        </div>
      </div>
      <div class="evidence-pair">
        ${evidenceCard(relation.left, "Source A")}
        <div class="pair-link">↔</div>
        ${evidenceCard(relation.right, "Source B")}
      </div>
    </article>`).join("");
  list.querySelectorAll("[data-evidence]").forEach((button) => button.addEventListener("click", () => openEvidence(button.dataset.evidence)));
}

function renderFacts() {
  const query = byId("factSearch").value.trim().toLowerCase();
  const facts = state.facts.filter((fact) => [fact.subject, fact.predicate, fact.object_text, fact.document_name, ...fact.scope].join(" ").toLowerCase().includes(query));
  byId("factsTable").innerHTML = facts.map((fact) => `
    <tr>
      <td><button class="fact-link" data-evidence="${esc(fact.id)}">${esc(fact.subject)} · ${esc(fact.predicate)}</button>${scopeNote(fact)}</td>
      <td><strong>${esc(fact.object_text)}</strong>${normalizedValueNote(fact)}</td>
      <td>${esc(periodLabel(fact))}<span class="td-sub">${esc(fact.modality)}</span></td>
      <td>${esc(shortName(fact.document_name))}<span class="td-sub">PDF page ${fact.page_number}</span></td>
    </tr>`).join("") || `<tr><td colspan="4" class="empty-state">No facts match your search.</td></tr>`;
  byId("factsTable").querySelectorAll("[data-evidence]").forEach((button) => button.addEventListener("click", () => openEvidence(button.dataset.evidence)));
}

function renderDocuments() {
  byId("documentsGrid").innerHTML = state.documents.map((document) => `
    <article class="document-card">
      <div class="doc-icon">PDF</div>
      <h3>${esc(document.name)}</h3>
      <div class="document-meta"><span>${document.page_count} ${document.page_count === 1 ? "page" : "pages"}</span><span>·</span><span>${document.fact_count} source-backed ${document.fact_count === 1 ? "fact" : "facts"}</span><span>·</span><span>${esc(documentStatusLabel(document.status))}</span></div>
      <div class="source-status ${document.source_available ? "" : "unavailable"}">${document.source_available ? "● Original PDF available for page review" : "○ Original PDF unavailable"}</div>
    </article>`).join("");
}

function renderFailures() {
  const list = byId("failureList");
  if (!state.failures.length) {
    list.innerHTML = `<div class="empty-state">No items currently need review.</div>`;
    return;
  }
  list.innerHTML = state.failures.map((failure) => {
    const details = failure.details || {};
    const issueSummary = diagnosticIssues(details);
    return `
      <article class="failure-card">
        <div><span class="failure-tag">${esc(stageLabel(failure.stage))} · PDF p. ${esc(failure.page_number || "-")}</span><h3>${esc(failure.message)}</h3><p>${esc(details.handling || "This item was not added to Facts.")}</p></div>
        <div class="failure-details"><dl>
          ${diagnosticRow("Candidate", details.candidate)}
          ${diagnosticRow("Source text", details.extracted_fragment || details.quote)}
          ${diagnosticRow("Why it needs review", issueSummary)}
          ${diagnosticRow("Next step", details.next_step || "Review the source or try the document again.")}
        </dl></div>
      </article>`;
  }).join("");
}

function renderSummary() {
  byId("metricDocuments").textContent = state.summary.documents;
  byId("metricFacts").textContent = state.summary.facts;
  byId("metricRelations").textContent = state.summary.relations;
  byId("metricFailures").textContent = state.summary.failures;
}

function openEvidence(factId) {
  const fact = state.facts.find((item) => item.id === factId);
  if (!fact) return;
  byId("evidenceTitle").textContent = `${fact.subject} · ${fact.predicate}`;
  byId("evidenceMeta").innerHTML = [fact.document_name, `PDF page ${fact.page_number}`, periodLabel(fact), fact.modality].map((item) => `<span>${esc(item)}</span>`).join("");
  byId("evidenceQuote").textContent = `“${fact.evidence_quote}”`;
  const sourceContext = fact.extraction_note || visibleScope(fact).join(" · ");
  byId("evidenceContext").innerHTML = sourceContext
    ? `<strong>Source context:</strong> ${esc(sourceContext)}`
    : "The quoted words appear on the source page shown below.";
  byId("pdfFrameWrap").innerHTML = fact.source_available
    ? `<div class="page-preview-head"><span><i class="anchor-dot"></i>Exact words highlighted on the source page</span><a href="/api/documents/${encodeURIComponent(fact.document_id)}/file#page=${fact.page_number}" target="_blank" rel="noreferrer">Open PDF ↗</a></div><img class="page-preview" alt="${esc(fact.document_name)} page ${fact.page_number} with the evidence quote highlighted" src="/api/facts/${encodeURIComponent(fact.id)}/evidence-image" />`
    : `<div class="pdf-missing">The original PDF is not bundled with the repository. The verified quote, document name, and PDF page remain available as sample output.</div>`;
  const drawer = byId("evidenceDialog");
  drawer.querySelector(".drawer-card").scrollTop = 0;
  drawer.showModal();
}

async function refresh() {
  try {
    const [config, summary, documents, facts, relations, failures] = await Promise.all([
      api("/api/config"), api("/api/summary"), api("/api/documents"), api("/api/facts"), api("/api/relations"), api("/api/failures"),
    ]);
    Object.assign(state, { config, summary, documents, facts, relations, failures });
    renderSummary(); renderRelationships(); renderFacts(); renderDocuments(); renderFailures();
    byId("datasetBadge").textContent = {
      curated_source_verified: "VERIFIED DEMO WITH ORIGINAL SOURCES",
      mixed: "DEMO + YOUR DOCUMENTS",
      workspace: "YOUR DOCUMENTS",
    }[config.dataset_origin] || "DOCUMENTS UNAVAILABLE";
    byId("datasetName").textContent = config.dataset_name.toUpperCase();
    byId("datasetStatus").textContent = config.demo_only ? "Sources included" : "Ready";
    byId("datasetNote").textContent = config.demo_only
      ? "Open a source below to inspect its original page and highlighted quote."
      : "Open any relationship or fact to inspect its source page.";
    byId("processingMode").className = `mode-note ${config.live_processing ? "" : "offline"}`;
    byId("processingMode").textContent = config.demo_only
      ? "The hosted demo is read-only. Follow the setup guide to process PDFs on your computer."
      : config.live_processing
        ? "PDF processing is ready. Documents already seen will not be processed twice."
        : `Add ${config.credential} to .env and restart the server to process new PDFs.`;
    byId("uploadTitle").textContent = config.demo_only ? "Use your PDFs locally" : "Use your PDFs";
    byId("pdfFiles").disabled = config.demo_only;
    byId("dropZone").classList.toggle("disabled", config.demo_only);
    byId("dropTitle").textContent = config.demo_only
      ? "Uploads are disabled in the public demonstration"
      : "Drop PDFs here or click to browse";
    byId("dropHint").textContent = config.demo_only
      ? "Clone the repository and follow its setup instructions to process new documents."
      : "Up to 50 MB each. A document already added will not be processed twice.";
    byId("publicSetupLink").classList.toggle("hidden", !config.demo_only);
    byId("processFiles").classList.toggle("hidden", config.demo_only);
    byId("processFiles").textContent = "Process PDFs";
    byId("processFiles").disabled = !config.live_processing;

    if (!state.viewInitialized) {
      const preferredView = relations.length
        ? "relationships"
        : facts.length
          ? "facts"
          : failures.length
            ? "diagnostics"
            : documents.length
              ? "documents"
              : null;
      if (preferredView) {
        switchView(preferredView);
        state.viewInitialized = true;
      }
    }
  } catch (error) {
    showToast(error.message);
  }
}

function switchView(name) {
  document.querySelectorAll(".nav-tab").forEach((tab) => {
    const selected = tab.dataset.view === name;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-pressed", selected);
  });
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === `${name}View`));
}

function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 3600);
}

function updateSelectedFiles() {
  const files = [...byId("pdfFiles").files];
  byId("selectedFiles").innerHTML = files.map((file) => `<div class="selected-file"><span>${esc(file.name)}</span><span>${(file.size / 1024 / 1024).toFixed(1)} MB</span></div>`).join("");
}

async function pollJob(jobId) {
  const progress = byId("jobProgress");
  progress.classList.remove("hidden");
  while (true) {
    const job = await api(`/api/jobs/${jobId}`);
    const percent = job.total ? Math.round((job.current / job.total) * 100) : job.status === "complete" ? 100 : 8;
    byId("jobMessage").textContent = job.message;
    byId("jobPercent").textContent = `${percent}%`;
    byId("jobBar").value = percent;
    if (job.status === "complete") {
      const issues = (job.results || []).filter((result) => result.status !== "ready");
      const resultNote = issues.length
        ? `${issues.length} document${issues.length === 1 ? "" : "s"} need review`
        : `${job.relations_added || 0} comparisons added`;
      showToast(`Processing complete · ${resultNote}`);
      await refresh();
      setTimeout(() => byId("uploadDialog").close(), 700);
      return;
    }
    if (job.status === "failed") throw new Error(job.message);
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

async function processUploads() {
  const files = [...byId("pdfFiles").files];
  if (!files.length) return showToast("Choose at least one PDF first.");
  const data = new FormData();
  files.forEach((file) => data.append("files", file));
  byId("processFiles").disabled = true;
  try {
    const job = await api("/api/uploads", { method: "POST", body: data });
    await pollJob(job.id);
  } catch (error) {
    showToast(error.message);
  } finally {
    byId("processFiles").disabled = !state.config.live_processing;
  }
}

document.querySelectorAll(".nav-tab").forEach((tab) => tab.addEventListener("click", () => {
  state.viewInitialized = true;
  switchView(tab.dataset.view);
}));
document.querySelectorAll("#relationFilters .filter").forEach((button) => button.addEventListener("click", () => {
  state.relationFilter = button.dataset.filter;
  document.querySelectorAll("#relationFilters .filter").forEach((item) => item.classList.toggle("active", item === button));
  renderRelationships();
}));
byId("factSearch").addEventListener("input", renderFacts);
byId("openUpload").addEventListener("click", () => byId("uploadDialog").showModal());
byId("closeEvidence").addEventListener("click", () => byId("evidenceDialog").close());
byId("pdfFiles").addEventListener("change", updateSelectedFiles);
byId("processFiles").addEventListener("click", processUploads);

const dropZone = byId("dropZone");
["dragenter", "dragover"].forEach((event) => dropZone.addEventListener(event, (e) => { e.preventDefault(); dropZone.classList.add("drag"); }));
["dragleave", "drop"].forEach((event) => dropZone.addEventListener(event, (e) => { e.preventDefault(); dropZone.classList.remove("drag"); }));
dropZone.addEventListener("drop", (event) => {
  const transfer = new DataTransfer();
  [...event.dataTransfer.files].filter((file) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")).forEach((file) => transfer.items.add(file));
  byId("pdfFiles").files = transfer.files;
  updateSelectedFiles();
});

refresh();
