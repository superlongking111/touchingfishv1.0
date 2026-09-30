"""SQLite connection + migration runner."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("fishmate.db")

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    schedule_type TEXT NOT NULL,
    interval_minutes INTEGER,
    fixed_times_json TEXT,
    jitter_minutes INTEGER NOT NULL DEFAULT 0,
    active_window_json TEXT,
    message TEXT NOT NULL DEFAULT '',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    url TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    parser_config_json TEXT,
    last_fetch_at DATETIME,
    fail_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS content_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_hash TEXT NOT NULL UNIQUE,
    source_id INTEGER,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at DATETIME,
    summary TEXT,
    llm_score REAL,
    llm_reason TEXT,
    short_summary TEXT,
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(source_id) REFERENCES content_sources(id)
);

CREATE TABLE IF NOT EXISTS watch_roots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    recursive INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS file_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    root_id INTEGER NOT NULL,
    event_time DATETIME NOT NULL,
    event_type TEXT NOT NULL,
    path TEXT NOT NULL,
    old_path TEXT,
    size INTEGER,
    mtime DATETIME,
    sha256 TEXT,
    FOREIGN KEY(root_id) REFERENCES watch_roots(id)
);

CREATE TABLE IF NOT EXISTS fish_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,
    started_at DATETIME NOT NULL,
    ended_at DATETIME,
    planned_minutes INTEGER,
    end_reason TEXT
);

CREATE TABLE IF NOT EXISTS reminder_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reminder_id INTEGER,
    fired_at DATETIME NOT NULL,
    action TEXT NOT NULL DEFAULT 'shown',
    acted_at DATETIME,
    FOREIGN KEY(reminder_id) REFERENCES reminders(id)
);

CREATE TABLE IF NOT EXISTS exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    zip_path TEXT NOT NULL,
    zip_sha256 TEXT,
    file_count INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER NOT NULL DEFAULT 0,
    mail_status TEXT
);

CREATE INDEX IF NOT EXISTS idx_file_events_time ON file_events(event_time);
CREATE INDEX IF NOT EXISTS idx_file_events_path ON file_events(path);
CREATE INDEX IF NOT EXISTS idx_content_items_status ON content_items(status);
CREATE INDEX IF NOT EXISTS idx_reminder_events_fired ON reminder_events(fired_at);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.path),
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def execute(self, sql: str, params: Iterable = ()) -> sqlite3.Cursor:
        cur = self.connect().execute(sql, tuple(params))
        self._conn.commit()  # type: ignore[union-attr]
        return cur

    def executemany(self, sql: str, seq: Iterable) -> sqlite3.Cursor:
        cur = self.connect().executemany(sql, list(seq))
        self._conn.commit()  # type: ignore[union-attr]
        return cur

    def query(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        cur = self.connect().execute(sql, tuple(params))
        return cur.fetchall()

    def query_one(self, sql: str, params: Iterable = ()) -> sqlite3.Row | None:
        cur = self.connect().execute(sql, tuple(params))
        return cur.fetchone()

    def migrate(self) -> None:
        conn = self.connect()
        conn.executescript(SCHEMA_V1)
        row = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()
        current = row["version"] if row else 0
        if current < 1:
            conn.execute(
                "INSERT INTO schema_migrations(version) VALUES (1)"
            )
            conn.commit()
            logger.info("Applied migration v1")
        logger.info("Database ready at %s", self.path)
