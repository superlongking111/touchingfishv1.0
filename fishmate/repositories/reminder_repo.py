from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .db import Database


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


DEFAULT_REMINDERS = [
    {
        "type": "water",
        "name": "喝水",
        "enabled": 1,
        "schedule_type": "interval",
        "interval_minutes": 45,
        "fixed_times_json": None,
        "jitter_minutes": 5,
        "active_window_json": json.dumps({"start": "09:00", "end": "19:00"}),
        "message": "该喝水了",
    },
    {
        "type": "walk",
        "name": "走动",
        "enabled": 1,
        "schedule_type": "interval",
        "interval_minutes": 70,
        "fixed_times_json": None,
        "jitter_minutes": 8,
        "active_window_json": json.dumps({"start": "09:00", "end": "19:00"}),
        "message": "起来晃两圈",
    },
    {
        "type": "rest",
        "name": "玩手机/休息",
        "enabled": 1,
        "schedule_type": "interval",
        "interval_minutes": 90,
        "fixed_times_json": None,
        "jitter_minutes": 10,
        "active_window_json": json.dumps({"start": "09:00", "end": "19:00"}),
        "message": "小摸一下？建议休息 5 分钟",
    },
    {
        "type": "toilet",
        "name": "厕所",
        "enabled": 1,
        "schedule_type": "fixed",
        "interval_minutes": None,
        "fixed_times_json": json.dumps(["10:30", "15:30"]),
        "jitter_minutes": 0,
        "active_window_json": json.dumps({"start": "09:00", "end": "19:00"}),
        "message": "到点了",
    },
]


@dataclass
class Reminder:
    id: int
    type: str
    name: str
    enabled: bool
    schedule_type: str
    interval_minutes: int | None
    fixed_times: list[str]
    jitter_minutes: int
    active_window: dict[str, str]
    message: str

    @classmethod
    def from_row(cls, row: Any) -> "Reminder":
        fixed = json.loads(row["fixed_times_json"] or "[]")
        window = json.loads(row["active_window_json"] or '{"start":"09:00","end":"19:00"}')
        return cls(
            id=row["id"],
            type=row["type"],
            name=row["name"],
            enabled=bool(row["enabled"]),
            schedule_type=row["schedule_type"],
            interval_minutes=row["interval_minutes"],
            fixed_times=fixed,
            jitter_minutes=row["jitter_minutes"] or 0,
            active_window=window,
            message=row["message"] or "",
        )


class ReminderRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def seed_defaults(self) -> None:
        count = self.db.query_one("SELECT COUNT(*) AS c FROM reminders")
        if count and count["c"] > 0:
            return
        for r in DEFAULT_REMINDERS:
            self.db.execute(
                """
                INSERT INTO reminders(
                  type,name,enabled,schedule_type,interval_minutes,
                  fixed_times_json,jitter_minutes,active_window_json,message,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    r["type"],
                    r["name"],
                    r["enabled"],
                    r["schedule_type"],
                    r["interval_minutes"],
                    r["fixed_times_json"],
                    r["jitter_minutes"],
                    r["active_window_json"],
                    r["message"],
                    _now(),
                ),
            )

    def list_all(self) -> list[Reminder]:
        rows = self.db.query("SELECT * FROM reminders ORDER BY id")
        return [Reminder.from_row(r) for r in rows]

    def list_enabled(self) -> list[Reminder]:
        return [r for r in self.list_all() if r.enabled]

    def get(self, reminder_id: int) -> Reminder | None:
        row = self.db.query_one("SELECT * FROM reminders WHERE id=?", (reminder_id,))
        return Reminder.from_row(row) if row else None

    def update(self, reminder: Reminder) -> None:
        self.db.execute(
            """
            UPDATE reminders SET
              name=?, enabled=?, schedule_type=?, interval_minutes=?,
              fixed_times_json=?, jitter_minutes=?, active_window_json=?,
              message=?, updated_at=?
            WHERE id=?
            """,
            (
                reminder.name,
                1 if reminder.enabled else 0,
                reminder.schedule_type,
                reminder.interval_minutes,
                json.dumps(reminder.fixed_times, ensure_ascii=False),
                reminder.jitter_minutes,
                json.dumps(reminder.active_window, ensure_ascii=False),
                reminder.message,
                _now(),
                reminder.id,
            ),
        )

    def create_custom(
        self,
        name: str,
        message: str,
        schedule_type: str,
        interval_minutes: int | None = None,
        fixed_times: list[str] | None = None,
        jitter_minutes: int = 0,
        active_window: dict[str, str] | None = None,
    ) -> int:
        window = active_window or {"start": "09:00", "end": "19:00"}
        cur = self.db.execute(
            """
            INSERT INTO reminders(
              type,name,enabled,schedule_type,interval_minutes,
              fixed_times_json,jitter_minutes,active_window_json,message,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "custom",
                name,
                1,
                schedule_type,
                interval_minutes,
                json.dumps(fixed_times or [], ensure_ascii=False),
                jitter_minutes,
                json.dumps(window, ensure_ascii=False),
                message,
                _now(),
            ),
        )
        return int(cur.lastrowid)

    def log_event(self, reminder_id: int | None, action: str = "shown") -> int:
        cur = self.db.execute(
            """
            INSERT INTO reminder_events(reminder_id, fired_at, action, acted_at)
            VALUES(?,?,?,?)
            """,
            (
                reminder_id,
                _now(),
                action,
                _now() if action != "shown" else None,
            ),
        )
        return int(cur.lastrowid)

    def update_event_action(self, event_id: int, action: str) -> None:
        self.db.execute(
            "UPDATE reminder_events SET action=?, acted_at=? WHERE id=?",
            (action, _now(), event_id),
        )

    def stats_today(self) -> dict[str, int]:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self.db.query(
            """
            SELECT r.type, re.action, COUNT(*) AS c
            FROM reminder_events re
            LEFT JOIN reminders r ON r.id = re.reminder_id
            WHERE date(re.fired_at)=?
            GROUP BY r.type, re.action
            """,
            (today,),
        )
        result: dict[str, int] = {"water": 0, "walk": 0, "toilet": 0, "rest_minutes": 0}
        for row in rows:
            t = row["type"] or "custom"
            if row["action"] in ("primary", "shown") and t in result:
                if t != "rest_minutes":
                    result[t] = result.get(t, 0) + int(row["c"])
            if t == "rest" and row["action"] == "primary":
                result["rest_minutes"] += 5 * int(row["c"])
        return result

    def clear_events(self) -> None:
        self.db.execute("DELETE FROM reminder_events")
