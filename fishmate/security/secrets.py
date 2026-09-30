"""API key storage via keyring (Windows Credential Manager)."""

from __future__ import annotations

import logging

logger = logging.getLogger("fishmate.secrets")

SERVICE_NAME = "FishMate"
LLM_KEY_USERNAME = "llm_api_key"
SMTP_KEY_USERNAME = "smtp_password"


class SecretStore:
    def __init__(self, service: str = SERVICE_NAME) -> None:
        self.service = service

    def set_llm_api_key(self, api_key: str) -> None:
        import keyring

        if not api_key:
            self.clear_llm_api_key()
            return
        keyring.set_password(self.service, LLM_KEY_USERNAME, api_key)

    def get_llm_api_key(self) -> str | None:
        try:
            import keyring

            return keyring.get_password(self.service, LLM_KEY_USERNAME)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read API key from keyring: %s", type(exc).__name__)
            return None

    def clear_llm_api_key(self) -> None:
        try:
            import keyring

            keyring.delete_password(self.service, LLM_KEY_USERNAME)
        except Exception:  # noqa: BLE001
            pass

    def set_smtp_password(self, password: str) -> None:
        import keyring

        if not password:
            self.clear_smtp_password()
            return
        keyring.set_password(self.service, SMTP_KEY_USERNAME, password)

    def get_smtp_password(self) -> str | None:
        try:
            import keyring

            return keyring.get_password(self.service, SMTP_KEY_USERNAME)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read SMTP password: %s", type(exc).__name__)
            return None

    def clear_smtp_password(self) -> None:
        try:
            import keyring

            keyring.delete_password(self.service, SMTP_KEY_USERNAME)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def mask(value: str | None) -> str:
        if not value:
            return ""
        if len(value) <= 8:
            return "*" * len(value)
        return value[:3] + "*" * (len(value) - 6) + value[-3:]
