"""Optional SMTP/OAuth adapter stub for V1.1 — not used by default."""

from __future__ import annotations

from .base import MailDraft, MailResult


class SmtpOAuthAdapter:
    """Placeholder for future Gmail/Outlook OAuth SMTP."""

    async def create_draft(self, mail: MailDraft) -> MailResult:
        return MailResult(False, "SMTP OAuth 适配器尚未启用（V1.1）")

    async def send(self, mail: MailDraft) -> MailResult:
        return MailResult(False, "SMTP OAuth 适配器尚未启用（V1.1）")
