"""Shared application context / service locator."""

from __future__ import annotations

from dataclasses import dataclass

from fishmate.repositories import (
    ContentRepo,
    Database,
    ExportRepo,
    ReminderRepo,
    SessionRepo,
    SettingsRepo,
    WorklogRepo,
)
from fishmate.security.path_policy import PathPolicy
from fishmate.security.secrets import SecretStore
from fishmate.services.hash_worker import HashWorker
from fishmate.services.llm_client import LLMClient


@dataclass
class AppContext:
    db: Database
    settings: SettingsRepo
    reminders: ReminderRepo
    content: ContentRepo
    worklog: WorklogRepo
    sessions: SessionRepo
    exports: ExportRepo
    secrets: SecretStore
    path_policy: PathPolicy
    hash_worker: HashWorker

    def build_llm_client(self) -> LLMClient | None:
        base = self.settings.get("llm_base_url") or ""
        model = self.settings.get("llm_model") or ""
        if not base or not model:
            return None
        return LLMClient(
            base_url=base,
            api_key=self.secrets.get_llm_api_key(),
            model=model,
            timeout=float(self.settings.get("llm_timeout", 30)),
            temperature=float(self.settings.get("llm_temperature", 0.3)),
        )

    def refresh_path_policy(self) -> None:
        patterns = self.settings.get("ignore_patterns") or []
        self.path_policy.set_ignore_patterns(list(patterns))
