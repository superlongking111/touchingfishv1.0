"""Send mail via SMTP (app password) — no Outlook / mailto."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from .base import MailDraft, MailResult

logger = logging.getLogger("fishmate.mail.smtp")


class SmtpMailClient:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        *,
        use_ssl: bool = True,
        timeout: float = 60.0,
    ) -> None:
        self.host = host.strip()
        self.port = int(port)
        self.username = username.strip()
        self.password = password
        self.use_ssl = use_ssl
        self.timeout = timeout

    def send_sync(self, mail: MailDraft) -> MailResult:
        if not self.host or not self.username or not self.password:
            return MailResult(False, "SMTP 未配置完整（主机、账号、授权码）")
        if not mail.to:
            return MailResult(False, "请填写收件人")
        try:
            msg = MIMEMultipart()
            msg["From"] = self.username
            msg["To"] = ", ".join(mail.to)
            if mail.cc:
                msg["Cc"] = ", ".join(mail.cc)
            msg["Subject"] = mail.subject
            msg.attach(MIMEText(mail.body, "plain", "utf-8"))
            for path in mail.attachments:
                p = Path(path)
                if not p.is_file():
                    continue
                part = MIMEBase("application", "octet-stream")
                part.set_payload(p.read_bytes())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=("utf-8", "", p.name),
                )
                msg.attach(part)
            recipients = list(mail.to) + list(mail.cc or [])
            if self.use_ssl and self.port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(
                    self.host, self.port, timeout=self.timeout, context=context
                ) as server:
                    server.login(self.username, self.password)
                    server.sendmail(self.username, recipients, msg.as_string())
            else:
                with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as server:
                    server.ehlo()
                    if self.use_ssl:
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                        server.ehlo()
                    server.login(self.username, self.password)
                    server.sendmail(self.username, recipients, msg.as_string())
            return MailResult(True, "邮件已通过 SMTP 发送", draft_created=False)
        except Exception as exc:  # noqa: BLE001
            logger.info("SMTP send failed: %s", type(exc).__name__)
            return MailResult(False, f"发送失败：{type(exc).__name__} — {exc}")
