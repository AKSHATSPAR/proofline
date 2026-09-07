from __future__ import annotations

import hashlib
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

import pymupdf
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from proofline.audit import grounding_audit
from proofline.demo import DEMO_PATH, load_demo
from proofline.llm import (
    create_extractor,
    provider_is_configured,
    provider_key_name,
    provider_model,
    provider_name,
)
from proofline.pipeline import KnowledgeLayer
from proofline.store import Store
from proofline.text import locate_evidence_rects

PACKAGE_ROOT = Path(__file__).parent
WEB_ROOT = PACKAGE_ROOT / "web"
PROJECT_ROOT = PACKAGE_ROOT.parents[1]
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="proofline-ingest")

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def submit(self, paths: list[Path], store: Store, provider: str, model: str) -> dict:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "status": "queued",
                "message": "Waiting to process",
                "current": 0,
                "total": 0,
                "results": [],
            }
        self._executor.submit(self._run, job_id, paths, store, provider, model)
        return self.get(job_id) or {}

    def _update(self, job_id: str, **values: object) -> None:
        with self._lock:
            self._jobs[job_id].update(values)

    def _run(self, job_id: str, paths: list[Path], store: Store, provider: str, model: str) -> None:
        self._update(job_id, status="running", message="Starting page-aware extraction")
        try:
            layer = KnowledgeLayer(store, create_extractor(provider=provider, model=model))
            results = []

            def progress(name: str, current: int, total: int) -> None:
                self._update(
                    job_id,
                    message=f"Extracting grounded facts from {name}",
                    current=current,
                    total=total,
                )

            for path in paths:
                result = layer.ingest_pdf(path, progress=progress)
                results.append(result.__dict__)
            self._update(
                job_id,
                message="Comparing cross-document candidates",
                current=0,
                total=0,
            )
            relations_added = layer.discover_relations(max_pairs=80)
            issue_count = sum(result.status != "ready" for result in results)
            message = (
                f"Finished with issues in {issue_count} of {len(results)} documents"
                if issue_count
                else "Knowledge layer updated"
            )
            self._update(
                job_id,
                status="complete",
                message=message,
                results=results,
                relations_added=relations_added,
            )
        except Exception as error:  # noqa: BLE001 - background job must retain its failure.
            self._update(job_id, status="failed", message=str(error))


def _fact_payload(fact, source_available: dict[str, bool]) -> dict:
    return {
        **fact.model_dump(mode="json"),
        "source_available": source_available.get(fact.document_id, False),
    }


def create_app(db_path: Path | None = None) -> FastAPI:
    load_dotenv()
    resolved_db = db_path or Path(os.getenv("PROOFLINE_DB_PATH", "data/proofline.db"))
    store = Store(resolved_db)
    if store.summary()["documents"] == 0:
        load_demo(store)
    jobs = JobManager()

    app = FastAPI(
        title="Proofline API",
        description="Page-grounded facts and explained cross-document relationships.",
        version="0.1.0",
    )
    app.state.store = store
    app.state.jobs = jobs

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/config")
    def config() -> dict:
        active_provider = provider_name()
        return {
            "live_processing": provider_is_configured(active_provider),
            "provider": active_provider,
            "credential": provider_key_name(active_provider),
            "model": provider_model(active_provider),
            "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
            "demo_name": "India macroeconomy",
        }

    @app.get("/api/summary")
    def summary() -> dict:
        counts = store.summary()
        relation_counts = {"corroborates": 0, "contradicts": 0, "reconciles": 0}
        for relation in store.relations():
            relation_counts[relation.relation_type.value] = (
                relation_counts.get(relation.relation_type.value, 0) + 1
            )
        return {**counts, "relation_types": relation_counts}

    @app.get("/api/documents")
    def documents() -> list[dict]:
        response = []
        for document in store.documents():
            source_path = document.pop("source_path", None)
            document["source_available"] = bool(source_path and Path(source_path).is_file())
            response.append(document)
        return response

    @app.get("/api/facts")
    def facts() -> list[dict]:
        source_available = {
            document["id"]: bool(
                document.get("source_path") and Path(document["source_path"]).is_file()
            )
            for document in store.documents()
        }
        return [_fact_payload(fact, source_available) for fact in store.facts()]

    @app.get("/api/relations")
    def relations() -> list[dict]:
        facts_by_id = {fact.id: fact for fact in store.facts()}
        source_available = {
            document["id"]: bool(
                document.get("source_path") and Path(document["source_path"]).is_file()
            )
            for document in store.documents()
        }
        response = []
        for relation in store.relations():
            left = facts_by_id.get(relation.left_fact_id)
            right = facts_by_id.get(relation.right_fact_id)
            if left is None or right is None:
                continue
            response.append(
                {
                    **relation.model_dump(mode="json"),
                    "left": _fact_payload(left, source_available),
                    "right": _fact_payload(right, source_available),
                }
            )
        return response

    @app.get("/api/failures")
    def failures() -> list[dict]:
        return store.failures()

    @app.get("/api/audits/grounding")
    def audit_grounding() -> dict:
        return grounding_audit(store)

    @app.get("/api/documents/{document_id}/pages/{page_number}")
    def page_text(document_id: str, page_number: int) -> dict:
        text = store.page_text(document_id, page_number)
        if text is None:
            raise HTTPException(status_code=404, detail="Page not found")
        return {"document_id": document_id, "page_number": page_number, "text": text}

    @app.get("/api/documents/{document_id}/file")
    def document_file(document_id: str) -> FileResponse:
        document = store.document(document_id)
        if not document or not document.get("source_path"):
            raise HTTPException(status_code=404, detail="Source PDF is not available locally")
        path = Path(document["source_path"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Source PDF is not available locally")
        return FileResponse(path, media_type="application/pdf", filename=document["name"])

    @app.get("/api/documents/{document_id}/pages/{page_number}/image")
    def document_page_image(document_id: str, page_number: int) -> Response:
        document = store.document(document_id)
        if not document or not document.get("source_path"):
            raise HTTPException(status_code=404, detail="Source PDF is not available locally")
        path = Path(document["source_path"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Source PDF is not available locally")
        with pymupdf.open(path) as pdf:
            if page_number < 1 or page_number > pdf.page_count:
                raise HTTPException(status_code=404, detail="Page not found")
            pixmap = pdf[page_number - 1].get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), alpha=False)
            image = pixmap.tobytes("png")
        return Response(
            content=image,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/api/facts/{fact_id}/evidence-image")
    def fact_evidence_image(fact_id: str) -> Response:
        fact = store.fact(fact_id)
        if fact is None:
            raise HTTPException(status_code=404, detail="Fact not found")
        document = store.document(fact.document_id)
        if not document or not document.get("source_path"):
            raise HTTPException(status_code=404, detail="Source PDF is not available locally")
        path = Path(document["source_path"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Source PDF is not available locally")

        with pymupdf.open(path) as pdf:
            if fact.page_number < 1 or fact.page_number > pdf.page_count:
                raise HTTPException(status_code=404, detail="Evidence page not found")
            page = pdf[fact.page_number - 1]
            rects = locate_evidence_rects(page, fact.evidence_quote)
            if rects:
                annotation = page.add_highlight_annot(rects)
                annotation.set_colors(stroke=(0.95, 0.49, 0.08))
                annotation.set_opacity(0.42)
                annotation.update()
                page = pdf.reload_page(page)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), alpha=False)
            image = pixmap.tobytes("png")

        return Response(
            content=image,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600",
                "X-Proofline-Evidence-Spans": str(len(rects)),
                "X-Proofline-Evidence-Status": "located" if rects else "not-located",
            },
        )

    @app.post("/api/demo")
    def seed_demo() -> dict:
        added = load_demo(store, DEMO_PATH)
        return {"added": added, **store.summary()}

    @app.post("/api/uploads", status_code=202)
    async def upload_pdfs(files: Annotated[list[UploadFile], File()]) -> dict:
        active_provider = provider_name()
        if not provider_is_configured(active_provider):
            key_name = provider_key_name(active_provider)
            raise HTTPException(
                status_code=503,
                detail=f"Set {key_name} in the server environment to process new PDFs.",
            )
        if not files:
            raise HTTPException(status_code=400, detail="Upload at least one PDF")

        upload_root = PROJECT_ROOT / "data" / "uploads"
        upload_root.mkdir(parents=True, exist_ok=True)
        saved_paths: list[Path] = []
        for upload in files:
            content = await upload.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail=f"{upload.filename} exceeds 50 MB")
            if not content.startswith(b"%PDF-"):
                raise HTTPException(status_code=415, detail=f"{upload.filename} is not a PDF")
            digest = hashlib.sha256(content).hexdigest()
            safe_name = Path(upload.filename or "document.pdf").name
            destination = upload_root / f"{digest[:12]}-{safe_name}"
            destination.write_bytes(content)
            saved_paths.append(destination)

        job = jobs.submit(
            saved_paths,
            store,
            provider=active_provider,
            model=provider_model(active_provider),
        )
        return job

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    app.mount("/assets", StaticFiles(directory=WEB_ROOT), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_ROOT / "index.html")

    return app


app = create_app()


def main() -> None:
    uvicorn.run("proofline.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
