from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .db import Database


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class ExportRecord:
    id: int
    created_at: str
    zip_path: str
    zip_sha256: str | None
    file_count: int
    total_bytes: int
    mail_status: str | None


class ExportRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        zip_path: str,
        zip_sha256: str | None,
        file_count: int,
        total_bytes: int,
        mail_status: str | None = None,
    ) -> int:
        cur = self.db.execute(
            """
            INSERT INTO exports(created_at,zip_path,zip_sha256,file_count,total_bytes,mail_status)
            VALUES(?,?,?,?,?,?)
            """,
            (_now(), zip_path, zip_sha256, file_count, total_bytes, mail_status),
        )
        return int(cur.lastrowid)

    def update_mail_status(self, export_id: int, status: str) -> None:
        self.db.execute(
            "UPDATE exports SET mail_status=? WHERE id=?",
            (status, export_id),
        )

    def list_recent(self, limit: int = 20) -> list[ExportRecord]:
        rows = self.db.query(
            "SELECT * FROM exports ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [self._e(r) for r in rows]

    def clear(self) -> None:
        self.db.execute("DELETE FROM exports")

    @staticmethod
    def _e(r: Any) -> ExportRecord:
        return ExportRecord(
            id=r["id"],
            created_at=r["created_at"],
            zip_path=r["zip_path"],
            zip_sha256=r["zip_sha256"],
            file_count=r["file_count"],
            total_bytes=r["total_bytes"],
            mail_status=r["mail_status"],
        )
