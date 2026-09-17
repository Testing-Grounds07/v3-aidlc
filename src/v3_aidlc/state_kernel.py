"""Minimal canonical state kernel for the V3-AIDLC bootstrap project."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class StatePaths:
    root: Path
    project_id: str

    @property
    def project_dir(self) -> Path:
        return self.root / "projects" / self.project_id

    @property
    def database(self) -> Path:
        return self.project_dir / "state.db"

    @property
    def evidence_dir(self) -> Path:
        return self.project_dir / "evidence"

    @property
    def artifacts_dir(self) -> Path:
        return self.project_dir / "artifacts"

    @property
    def exports_dir(self) -> Path:
        return self.project_dir / "exports"

    @property
    def config_dir(self) -> Path:
        return self.project_dir / "config"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    entity_type TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id),
    source_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, source_id, relationship_type, target_id)
);

CREATE TABLE IF NOT EXISTS events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL REFERENCES projects(id),
    event_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    summary TEXT NOT NULL,
    rationale TEXT NOT NULL,
    authority TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class StateKernel:
    def __init__(self, paths: StatePaths):
        self.paths = paths

    def initialize_directories(self) -> None:
        for path in (
            self.paths.project_dir,
            self.paths.evidence_dir,
            self.paths.artifacts_dir,
            self.paths.exports_dir,
            self.paths.config_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.paths.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize_schema(self) -> None:
        self.initialize_directories()
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                ("schema_version", SCHEMA_VERSION),
            )

    def upsert_project(self, name: str, status: str) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO projects(id, name, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (self.paths.project_id, name, status, now, now),
            )

    def upsert_entity(
        self,
        entity_id: str,
        entity_type: str,
        title: str,
        status: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        attributes_json = json.dumps(attributes or {}, sort_keys=True)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO entities(
                    id, project_id, entity_type, title, status,
                    attributes_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    entity_type = excluded.entity_type,
                    title = excluded.title,
                    status = excluded.status,
                    attributes_json = excluded.attributes_json,
                    updated_at = excluded.updated_at
                """,
                (
                    entity_id,
                    self.paths.project_id,
                    entity_type,
                    title,
                    status,
                    attributes_json,
                    now,
                    now,
                ),
            )

    def relate(self, source_id: str, relationship_type: str, target_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO relationships(
                    project_id, source_id, relationship_type, target_id, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.paths.project_id,
                    source_id,
                    relationship_type,
                    target_id,
                    utc_now(),
                ),
            )

    def append_event(
        self,
        event_id: str,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO events(
                    event_id, project_id, event_type, aggregate_type,
                    aggregate_id, payload_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    self.paths.project_id,
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    json.dumps(payload or {}, sort_keys=True),
                    utc_now(),
                ),
            )

    def record_decision(
        self,
        decision_id: str,
        summary: str,
        rationale: str,
        authority: str = "user",
        status: str = "accepted",
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO decisions(
                    id, project_id, summary, rationale, authority, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    self.paths.project_id,
                    summary,
                    rationale,
                    authority,
                    status,
                    utc_now(),
                ),
            )

    def snapshot(self) -> dict[str, Any]:
        with self.connect() as connection:
            project_row = connection.execute(
                "SELECT * FROM projects WHERE id = ?", (self.paths.project_id,)
            ).fetchone()
            if project_row is None:
                raise ValueError(f"Unknown project: {self.paths.project_id}")

            entities = []
            for row in connection.execute(
                "SELECT * FROM entities WHERE project_id = ? ORDER BY entity_type, id",
                (self.paths.project_id,),
            ):
                item = dict(row)
                item["attributes"] = json.loads(item.pop("attributes_json"))
                entities.append(item)

            relationships = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT source_id, relationship_type, target_id, created_at
                    FROM relationships
                    WHERE project_id = ?
                    ORDER BY id
                    """,
                    (self.paths.project_id,),
                )
            ]
            decisions = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM decisions WHERE project_id = ? ORDER BY created_at, id",
                    (self.paths.project_id,),
                )
            ]
            events = []
            for row in connection.execute(
                "SELECT * FROM events WHERE project_id = ? ORDER BY sequence",
                (self.paths.project_id,),
            ):
                item = dict(row)
                item["payload"] = json.loads(item.pop("payload_json"))
                events.append(item)

        database_hash = hashlib.sha256(self.paths.database.read_bytes()).hexdigest()
        return {
            "schemaVersion": SCHEMA_VERSION,
            "generatedAt": utc_now(),
            "snapshotAuthority": False,
            "stateAuthority": "state.db",
            "databaseSha256": database_hash,
            "project": dict(project_row),
            "entities": entities,
            "relationships": relationships,
            "decisions": decisions,
            "events": events,
        }

    def write_snapshot(self) -> Path:
        snapshot_path = self.paths.exports_dir / "project-state.json"
        snapshot_path.write_text(
            json.dumps(self.snapshot(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return snapshot_path

