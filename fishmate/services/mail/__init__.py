from .base import MailAdapter, MailDraft, MailResult
from .default_client import DefaultMailClient
from .smtp_client import SmtpMailClient

__all__ = ["MailAdapter", "MailDraft", "MailResult", "DefaultMailClient", "SmtpMailClient"]
