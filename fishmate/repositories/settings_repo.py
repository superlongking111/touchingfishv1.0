from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .db import Database


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


DEFAULT_SETTINGS: dict[str, Any] = {
    "onboarding_done": False,
    "ui_theme": "light",
    "autostart": False,
    "notification_fade_seconds": 10,
    "reminder_snooze_minutes": 10,
    "defer_when_fullscreen": True,
    "data_retention_days": 90,
    "today_topic": "",
    "content_fetch_min_minutes": 35,
    "content_fetch_max_minutes": 90,
    "content_daily_limit": 6,
    "content_dedupe_days": 7,
    "modify_debounce_seconds": 5,
    "hash_max_bytes": 2 * 1024 * 1024 * 1024,
    "ignore_patterns": [
        "~$*",
        "*.tmp",
        "*.swp",
        ".git",
        "node_modules",
        "__pycache__",
        ".DS_Store",
        "Thumbs.db",
    ],
    "sensitive_extensions": [".pem", ".key", ".p12", ".pfx", ".env"],
    "llm_provider_name": "OpenAI Compatible",
    "llm_base_url": "https://api.openai.com/v1",
    "llm_model": "gpt-4o-mini",
    "llm_timeout": 60,
    "llm_temperature": 0.3,
    "llm_score_threshold": 0.55,
    "active_window": {"start": "09:00", "end": "19:00"},
    "reminders_paused_until": None,
    "fish_paused": False,
    "mail_smtp_host": "",
    "mail_smtp_port": 465,
    "mail_smtp_user": "",
    "mail_smtp_to": "",
    "mail_smtp_use_ssl": True,
    "offline": False,
    "content_preset_revision": 0,
}


class SettingsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.query_one("SELECT value_json FROM settings WHERE key=?", (key,))
        if not row:
            return DEFAULT_SETTINGS.get(key, default)
        try:
            return json.loads(row["value_json"])
        except json.JSONDecodeError:
            return default

    def set(self, key: str, value: Any) -> None:
        self.db.execute(
            """
            INSERT INTO settings(key, value_json, updated_at)
            VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET
              value_json=excluded.value_json,
              updated_at=excluded.updated_at
            """,
            (key, json.dumps(value, ensure_ascii=False), _now()),
        )

    def get_all(self) -> dict[str, Any]:
        result = dict(DEFAULT_SETTINGS)
        for row in self.db.query("SELECT key, value_json FROM settings"):
            try:
                result[row["key"]] = json.loads(row["value_json"])
            except json.JSONDecodeError:
                continue
        return result

    def ensure_defaults(self) -> None:
        for key, value in DEFAULT_SETTINGS.items():
            row = self.db.query_one("SELECT 1 FROM settings WHERE key=?", (key,))
            if not row:
                self.set(key, value)
