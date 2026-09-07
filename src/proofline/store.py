from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from proofline.schemas import StoredFact, StoredRelation

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    page_count INTEGER NOT NULL,
    source_path TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pages (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (document_id, page_number)
);

CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_text TEXT NOT NULL,
    value_type TEXT NOT NULL,
    value_number REAL,
    unit TEXT,
    normalized_value REAL,
    normalized_unit TEXT,
    period_start TEXT,
    period_end TEXT,
    as_of_date TEXT,
    scope_json TEXT NOT NULL,
    modality TEXT NOT NULL,
    comparison_key TEXT NOT NULL,
    evidence_quote TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    confidence REAL NOT NULL,
    extraction_note TEXT,
    evidence_status TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_facts_comparison_key ON facts(comparison_key);
CREATE INDEX IF NOT EXISTS idx_facts_document_id ON facts(document_id);

CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY,
    left_fact_id TEXT NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    right_fact_id TEXT NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    explanation TEXT NOT NULL,
    decisive_context_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(left_fact_id, right_fact_id)
);

CREATE TABLE IF NOT EXISTS failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    page_number INTEGER,
    chunk_index INTEGER,
    message TEXT NOT NULL,
    recoverable INTEGER NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(documents)").fetchall()
            }
            if "source_path" not in columns:
                connection.execute("ALTER TABLE documents ADD COLUMN source_path TEXT")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def document_by_hash(self, sha256: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM documents WHERE sha256 = ?", (sha256,)
            ).fetchone()

    def delete_document(self, document_id: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    def add_document(
        self,
        document_id: str,
        name: str,
        sha256: str,
        page_texts: list[tuple[int, str]],
        *,
        page_count: int | None = None,
        source_path: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO documents(id, name, sha256, page_count, source_path, status)
                VALUES (?, ?, ?, ?, ?, 'processing')
                """,
                (document_id, name, sha256, page_count or len(page_texts), source_path),
            )
            connection.executemany(
                "INSERT INTO pages(document_id, page_number, text) VALUES (?, ?, ?)",
                [(document_id, page, text) for page, text in page_texts],
            )

    def set_document_status(self, document_id: str, status: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE documents SET status = ? WHERE id = ?", (status, document_id)
            )

    def documents(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT d.*, COUNT(f.id) AS fact_count
                FROM documents d
                LEFT JOIN facts f ON f.document_id = d.id
                GROUP BY d.id
                ORDER BY d.created_at, d.name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def document(self, document_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        return dict(row) if row else None

    def page_text(self, document_id: str, page_number: int) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT text FROM pages WHERE document_id = ? AND page_number = ?",
                (document_id, page_number),
            ).fetchone()
        return row["text"] if row else None

    def add_fact(self, fact: StoredFact) -> bool:
        payload = fact.model_dump(mode="json")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO facts(
                    id, document_id, chunk_index, subject, predicate, object_text,
                    value_type, value_number, unit, normalized_value, normalized_unit,
                    period_start, period_end, as_of_date, scope_json, modality,
                    comparison_key, evidence_quote, page_number, confidence,
                    extraction_note, evidence_status, extraction_method
                ) VALUES (
                    :id, :document_id, :chunk_index, :subject, :predicate, :object_text,
                    :value_type, :value_number, :unit, :normalized_value, :normalized_unit,
                    :period_start, :period_end, :as_of_date, :scope_json, :modality,
                    :comparison_key, :evidence_quote, :page_number, :confidence,
                    :extraction_note, :evidence_status, :extraction_method
                )
                """,
                {**payload, "scope_json": json.dumps(payload.pop("scope"))},
            )
        return cursor.rowcount == 1

    def add_relation(self, relation: StoredRelation) -> None:
        payload = relation.model_dump(mode="json")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO relations(
                    id, left_fact_id, right_fact_id, relation_type, confidence,
                    explanation, decisive_context_json
                ) VALUES (
                    :id, :left_fact_id, :right_fact_id, :relation_type, :confidence,
                    :explanation, :decisive_context_json
                )
                """,
                {
                    **payload,
                    "decisive_context_json": json.dumps(payload.pop("decisive_context")),
                },
            )

    def add_failure(
        self,
        document_id: str | None,
        stage: str,
        message: str,
        *,
        page_number: int | None = None,
        chunk_index: int | None = None,
        recoverable: bool = True,
        details: dict | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO failures(
                    document_id, stage, page_number, chunk_index, message,
                    recoverable, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    stage,
                    page_number,
                    chunk_index,
                    message,
                    int(recoverable),
                    json.dumps(details or {}),
                ),
            )

    def facts(self) -> list[StoredFact]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT f.*, d.name AS document_name
                FROM facts f JOIN documents d ON d.id = f.document_id
                ORDER BY d.created_at, f.page_number, f.id
                """
            ).fetchall()
        return [self._fact_from_row(row) for row in rows]

    def relations(self) -> list[StoredRelation]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM relations ORDER BY confidence DESC, id"
            ).fetchall()
        return [
            StoredRelation(
                id=row["id"],
                left_fact_id=row["left_fact_id"],
                right_fact_id=row["right_fact_id"],
                relation_type=row["relation_type"],
                confidence=row["confidence"],
                explanation=row["explanation"],
                decisive_context=json.loads(row["decisive_context_json"]),
            )
            for row in rows
        ]

    def failures(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT x.*, d.name AS document_name
                FROM failures x
                LEFT JOIN documents d ON d.id = x.document_id
                ORDER BY x.created_at DESC, x.id DESC
                """
            ).fetchall()
        return [
            {
                **dict(row),
                "recoverable": bool(row["recoverable"]),
                "details": json.loads(row["details_json"]),
            }
            for row in rows
        ]

    def summary(self) -> dict[str, int]:
        with self.connect() as connection:
            return {
                "documents": connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
                "facts": connection.execute("SELECT COUNT(*) FROM facts").fetchone()[0],
                "relations": connection.execute("SELECT COUNT(*) FROM relations").fetchone()[0],
                "failures": connection.execute("SELECT COUNT(*) FROM failures").fetchone()[0],
            }

    @staticmethod
    def _fact_from_row(row: sqlite3.Row) -> StoredFact:
        return StoredFact(
            id=row["id"],
            document_id=row["document_id"],
            document_name=row["document_name"],
            chunk_index=row["chunk_index"],
            subject=row["subject"],
            predicate=row["predicate"],
            object_text=row["object_text"],
            value_type=row["value_type"],
            value_number=row["value_number"],
            unit=row["unit"],
            normalized_value=row["normalized_value"],
            normalized_unit=row["normalized_unit"],
            period_start=row["period_start"],
            period_end=row["period_end"],
            as_of_date=row["as_of_date"],
            scope=json.loads(row["scope_json"]),
            modality=row["modality"],
            comparison_key=row["comparison_key"],
            evidence_quote=row["evidence_quote"],
            page_number=row["page_number"],
            confidence=row["confidence"],
            extraction_note=row["extraction_note"],
            evidence_status=row["evidence_status"],
            extraction_method=row["extraction_method"],
        )
