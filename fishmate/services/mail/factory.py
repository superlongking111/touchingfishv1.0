"""Build mail client from app settings + keyring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .smtp_client import SmtpMailClient

if TYPE_CHECKING:
    from fishmate.app_context import AppContext


def smtp_client_from_context(ctx: AppContext) -> SmtpMailClient | None:
    host = (ctx.settings.get("mail_smtp_host") or "").strip()
    user = (ctx.settings.get("mail_smtp_user") or "").strip()
    pwd = ctx.secrets.get_smtp_password()
    if not host or not user or not pwd:
        return None
    port = int(ctx.settings.get("mail_smtp_port") or 465)
    use_ssl = bool(ctx.settings.get("mail_smtp_use_ssl", True))
    return SmtpMailClient(host, port, user, pwd, use_ssl=use_ssl)
