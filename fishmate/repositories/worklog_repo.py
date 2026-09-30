from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .db import Database


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class WatchRoot:
    id: int
    path: str
    enabled: bool
    recursive: bool
    created_at: str


@dataclass
class FileEvent:
    id: int
    root_id: int
    event_time: str
    event_type: str
    path: str
    old_path: str | None
    size: int | None
    mtime: str | None
    sha256: str | None


class WorklogRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list_roots(self, enabled_only: bool = False) -> list[WatchRoot]:
        sql = "SELECT * FROM watch_roots"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY id"
        return [
            WatchRoot(
                id=r["id"],
                path=r["path"],
                enabled=bool(r["enabled"]),
                recursive=bool(r["recursive"]),
                created_at=r["created_at"],
            )
            for r in self.db.query(sql)
        ]

    def add_root(self, path: str, recursive: bool = True) -> int:
        cur = self.db.execute(
            """
            INSERT INTO watch_roots(path, enabled, recursive, created_at)
            VALUES(?,?,?,?)
            ON CONFLICT(path) DO UPDATE SET enabled=1, recursive=excluded.recursive
            """,
            (path, 1, 1 if recursive else 0, _now()),
        )
        row = self.db.query_one("SELECT id FROM watch_roots WHERE path=?", (path,))
        return int(row["id"]) if row else int(cur.lastrowid)

    def remove_root(self, root_id: int) -> None:
        self.db.execute("UPDATE watch_roots SET enabled=0 WHERE id=?", (root_id,))

    def delete_root(self, root_id: int) -> None:
        self.db.execute("DELETE FROM watch_roots WHERE id=?", (root_id,))

    def insert_event(
        self,
        root_id: int,
        event_type: str,
        path: str,
        old_path: str | None = None,
        size: int | None = None,
        mtime: str | None = None,
        sha256: str | None = None,
        event_time: str | None = None,
    ) -> int:
        cur = self.db.execute(
            """
            INSERT INTO file_events(
              root_id,event_time,event_type,path,old_path,size,mtime,sha256
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                root_id,
                event_time or _now(),
                event_type,
                path,
                old_path,
                size,
                mtime,
                sha256,
            ),
        )
        return int(cur.lastrowid)

    def update_sha256(self, event_id: int, sha256: str) -> None:
        self.db.execute(
            "UPDATE file_events SET sha256=? WHERE id=?",
            (sha256, event_id),
        )

    def recent_modify(self, path: str, within_seconds: int) -> FileEvent | None:
        cutoff = (
            datetime.now() - timedelta(seconds=within_seconds)
        ).isoformat(timespec="seconds")
        row = self.db.query_one(
            """
            SELECT * FROM file_events
            WHERE path=? AND event_type='MODIFY' AND event_time>=?
            ORDER BY event_time DESC LIMIT 1
            """,
            (path, cutoff),
        )
        return self._event(row) if row else None

    def update_event_meta(
        self,
        event_id: int,
        size: int | None,
        mtime: str | None,
        event_time: str | None = None,
    ) -> None:
        self.db.execute(
            """
            UPDATE file_events SET size=?, mtime=?, event_time=COALESCE(?, event_time)
            WHERE id=?
            """,
            (size, mtime, event_time, event_id),
        )

    def list_events(
        self,
        date: str | None = None,
        event_type: str | None = None,
        limit: int = 500,
    ) -> list[FileEvent]:
        clauses = []
        params: list[Any] = []
        if date:
            clauses.append("date(event_time)=?")
            params.append(date)
        if event_type:
            clauses.append("event_type=?")
            params.append(event_type)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self.db.query(
            f"SELECT * FROM file_events{where} ORDER BY event_time DESC LIMIT ?",
            params,
        )
        return [self._event(r) for r in rows]

    def events_for_day(self, date: str | None = None) -> list[FileEvent]:
        d = date or datetime.now().strftime("%Y-%m-%d")
        return list(reversed(self.list_events(date=d, limit=2000)))

    def span_for_day(self, date: str | None = None) -> tuple[str | None, str | None]:
        d = date or datetime.now().strftime("%Y-%m-%d")
        row = self.db.query_one(
            """
            SELECT MIN(event_time) AS first_t, MAX(event_time) AS last_t
            FROM file_events WHERE date(event_time)=?
            """,
            (d,),
        )
        if not row:
            return None, None
        return row["first_t"], row["last_t"]

    def purge_older_than(self, days: int) -> int:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        cur = self.db.execute(
            "DELETE FROM file_events WHERE event_time < ?",
            (cutoff,),
        )
        return cur.rowcount

    def clear_events(self) -> None:
        self.db.execute("DELETE FROM file_events")

    @staticmethod
    def _event(r: Any) -> FileEvent:
        return FileEvent(
            id=r["id"],
            root_id=r["root_id"],
            event_time=r["event_time"],
            event_type=r["event_type"],
            path=r["path"],
            old_path=r["old_path"],
            size=r["size"],
            mtime=r["mtime"],
            sha256=r["sha256"],
        )
