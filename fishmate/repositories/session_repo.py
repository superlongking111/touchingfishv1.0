from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .db import Database


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class FishSession:
    id: int
    mode: str
    started_at: str
    ended_at: str | None
    planned_minutes: int | None
    end_reason: str | None


class SessionRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def start(self, mode: str, planned_minutes: int | None) -> int:
        # Close any dangling open session
        open_one = self.get_open()
        if open_one:
            self.end(open_one.id, "app_restart")
        cur = self.db.execute(
            """
            INSERT INTO fish_sessions(mode, started_at, planned_minutes)
            VALUES(?,?,?)
            """,
            (mode, _now(), planned_minutes),
        )
        return int(cur.lastrowid)

    def end(self, session_id: int, reason: str) -> None:
        self.db.execute(
            """
            UPDATE fish_sessions SET ended_at=?, end_reason=?
            WHERE id=? AND ended_at IS NULL
            """,
            (_now(), reason, session_id),
        )

    def extend(self, session_id: int, extra_minutes: int) -> None:
        row = self.db.query_one(
            "SELECT planned_minutes FROM fish_sessions WHERE id=?",
            (session_id,),
        )
        if not row:
            return
        planned = row["planned_minutes"]
        if planned is None:
            return
        self.db.execute(
            "UPDATE fish_sessions SET planned_minutes=? WHERE id=?",
            (planned + extra_minutes, session_id),
        )

    def get_open(self) -> FishSession | None:
        row = self.db.query_one(
            """
            SELECT * FROM fish_sessions
            WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1
            """
        )
        return self._s(row) if row else None

    def today_stats(self) -> dict[str, Any]:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self.db.query(
            """
            SELECT * FROM fish_sessions
            WHERE mode='big' AND date(started_at)=?
            """,
            (today,),
        )
        total_seconds = 0
        count = 0
        for r in rows:
            count += 1
            start = datetime.fromisoformat(r["started_at"])
            end = (
                datetime.fromisoformat(r["ended_at"])
                if r["ended_at"]
                else datetime.now().astimezone()
            )
            total_seconds += max(0, int((end - start).total_seconds()))
        return {"count": count, "minutes": total_seconds // 60}

    def clear(self) -> None:
        self.db.execute("DELETE FROM fish_sessions")

    @staticmethod
    def _s(r: Any) -> FishSession:
        return FishSession(
            id=r["id"],
            mode=r["mode"],
            started_at=r["started_at"],
            ended_at=r["ended_at"],
            planned_minutes=r["planned_minutes"],
            end_reason=r["end_reason"],
        )
