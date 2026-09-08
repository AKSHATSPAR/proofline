const state = {
  config: null,
  summary: null,
  documents: [],
  facts: [],
  relations: [],
  failures: [],
  audit: null,
  relationFilter: "all",
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
  return "Period not explicit";
}

function shortName(name) {
  return String(name).replace(/^\d+-/, "").replace(/-excerpt\.pdf$/i, "").replace(/\.pdf$/i, "").replaceAll("-", " ");
}

function confidenceLabel(value) {
  if (value >= 0.85) return "High";
  if (value >= 0.65) return "Medium";
  return "Low";
}

function normalizedValueNote(fact) {
  if (fact.normalized_value === null || fact.normalized_value === undefined) return "";
  const normalized = `${fact.normalized_value} ${fact.normalized_unit || ""}`.trim();
  if (!normalized || normalized.toLowerCase() === String(fact.object_text).trim().toLowerCase()) return "";
  return `<span class="td-sub">Normalized: ${esc(normalized)}</span>`;
}

function relationTitle(relation) {
  const labels = {
    corroborates: "Separate publications converge",
    contradicts: "Same claim, incompatible values",
    reconciles: "Context resolves the mismatch",
  };
  return `${labels[relation.relation_type]}: ${relation.left.predicate}`;
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
        <div class="confidence"><strong>${confidenceLabel(relation.confidence)}</strong><span>review signal</span></div>
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
      <td><button class="fact-link" data-evidence="${esc(fact.id)}">${esc(fact.subject)} · ${esc(fact.predicate)}</button><span class="td-sub">${esc(fact.scope.join(" · "))}</span></td>
      <td><strong>${esc(fact.object_text)}</strong>${normalizedValueNote(fact)}</td>
      <td>${esc(periodLabel(fact))}<span class="td-sub">${esc(fact.modality)}</span></td>
      <td>${esc(shortName(fact.document_name))}<span class="td-sub">PDF page ${fact.page_number}</span></td>
      <td>${confidenceLabel(fact.confidence)}<div class="confidence-bar"><i style="width:${Math.round(fact.confidence * 100)}%"></i></div></td>
    </tr>`).join("") || `<tr><td colspan="5" class="empty-state">No facts match your search.</td></tr>`;
  byId("factsTable").querySelectorAll("[data-evidence]").forEach((button) => button.addEventListener("click", () => openEvidence(button.dataset.evidence)));
}

function renderDocuments() {
  byId("documentsGrid").innerHTML = state.documents.map((document) => `
    <article class="document-card">
      <div class="doc-icon">PDF</div>
      <h3>${esc(document.name)}</h3>
      <div class="document-meta"><span>${document.page_count} pages</span><span>·</span><span>${document.fact_count} grounded facts</span><span>·</span><span>${esc(document.status)}</span></div>
      <div class="source-status ${document.source_available ? "" : "unavailable"}">${document.source_available ? "● Original PDF available for page review" : "○ Sample evidence retained; PDF not bundled"}</div>
    </article>`).join("");
}

function renderFailures() {
  const list = byId("failureList");
  if (!state.failures.length) {
    list.innerHTML = `<div class="empty-state">No extraction or reasoning failures are recorded.</div>`;
    return;
  }
  list.innerHTML = state.failures.map((failure) => {
    const details = failure.details || {};
    return `
      <article class="failure-card">
        <div><span class="failure-tag">${esc(failure.stage.replaceAll("_", " "))} · PDF p. ${esc(failure.page_number || "-")}</span><h3>${esc(failure.message)}</h3><p>${esc(details.handling || "The candidate was retained as a diagnostic and excluded from accepted facts.")}</p></div>
        <div class="failure-details"><dl><dt>Candidate</dt><dd>${esc(details.candidate || "-")}</dd><dt>Raw fragment</dt><dd>${esc(details.extracted_fragment || "-")}</dd><dt>Next step</dt><dd>${esc(details.next_step || "Inspect and retry with improved parsing.")}</dd></dl></div>
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
  byId("evidenceMeta").innerHTML = [fact.document_name, `PDF page ${fact.page_number}`, periodLabel(fact), `${confidenceLabel(fact.confidence)} extraction signal`, `Method: ${fact.extraction_method}`].map((item) => `<span>${esc(item)}</span>`).join("");
  byId("evidenceQuote").textContent = `“${fact.evidence_quote}”`;
  byId("evidenceContext").innerHTML = `<strong>Context:</strong> ${esc(fact.extraction_note || fact.scope.join(" · "))}<br /><strong>Comparison key:</strong> ${esc(fact.comparison_key)} · evidence match: ${esc(fact.evidence_status)}`;
  byId("pdfFrameWrap").innerHTML = fact.source_available
    ? `<div class="page-preview-head"><span><i class="anchor-dot"></i>Exact source span highlighted</span><a href="/api/documents/${encodeURIComponent(fact.document_id)}/file#page=${fact.page_number}" target="_blank" rel="noreferrer">Open PDF ↗</a></div><img class="page-preview" alt="${esc(fact.document_name)} page ${fact.page_number} with the evidence quote highlighted" src="/api/facts/${encodeURIComponent(fact.id)}/evidence-image" />`
    : `<div class="pdf-missing">The original PDF is not bundled with the repository. The verified quote, document name, and PDF page remain available as sample output.</div>`;
  const drawer = byId("evidenceDialog");
  drawer.querySelector(".drawer-card").scrollTop = 0;
  drawer.showModal();
}

async function refresh() {
  try {
    const [config, summary, documents, facts, relations, failures, audit] = await Promise.all([
      api("/api/config"), api("/api/summary"), api("/api/documents"), api("/api/facts"), api("/api/relations"), api("/api/failures"), api("/api/audits/grounding"),
    ]);
    Object.assign(state, { config, summary, documents, facts, relations, failures, audit });
    renderSummary(); renderRelationships(); renderFacts(); renderDocuments(); renderFailures();
    byId("fieldCoverage").textContent = `${audit.fields_grounded} / ${audit.accepted_facts} supported`;
    byId("wordAnchorCoverage").textContent = audit.source_available
      ? `${audit.word_anchored} / ${audit.source_available} located`
      : "Sources unavailable";
    byId("datasetBadge").textContent = {
      curated_source_verified: "CURATED, SOURCE-VERIFIED SAMPLE",
      mixed: "CURATED SAMPLE + PROCESSED WORKSPACE",
      workspace: "PROCESSED WORKSPACE",
    }[config.dataset_origin] || "DATASET ORIGIN UNAVAILABLE";
    byId("datasetStatus").textContent = config.demo_only ? "Curated review set" : "Workspace ready";
    byId("datasetNote").textContent = config.demo_only
      ? "These reviewed results are preloaded from the bundled source PDFs. Upload processing is available when the project runs locally."
      : "Results shown here come from this workspace and retain their document, page, and extraction method.";
    byId("processingMode").className = `mode-note ${config.live_processing ? "" : "offline"}`;
    byId("processingMode").textContent = config.demo_only
      ? "This public demonstration is read only so a shared key cannot be exhausted. Clone the repository to process your own PDFs."
      : config.live_processing
        ? `Live processing is enabled with ${config.provider}/${config.model}. Files are processed incrementally in the background.`
        : `Curated demo mode is active. Set ${config.credential} in .env and restart the server to process new PDFs.`;
    byId("pdfFiles").disabled = config.demo_only;
    byId("dropZone").classList.toggle("disabled", config.demo_only);
    byId("dropTitle").textContent = config.demo_only
      ? "Uploads are disabled in the public demonstration"
      : "Drop PDFs here or click to browse";
    byId("dropHint").textContent = config.demo_only
      ? "Clone the repository and follow its setup instructions to process new documents."
      : "Up to 50 MB each. Existing files are skipped by content hash.";
    byId("processFiles").textContent = config.demo_only ? "Available locally" : "Process PDFs";
    byId("processFiles").disabled = !config.live_processing;
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
        : `${job.relations_added || 0} relationships added`;
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

document.querySelectorAll(".nav-tab").forEach((tab) => tab.addEventListener("click", () => switchView(tab.dataset.view)));
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
