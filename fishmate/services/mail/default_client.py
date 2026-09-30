"""Open system default mail client with draft (mailto / Outlook COM / explorer)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

from .base import MailDraft, MailResult

logger = logging.getLogger("fishmate.mail")


class DefaultMailClient:
    """Prefer Outlook COM draft with attachments; fallback to mailto without attachments."""

    async def create_draft(self, mail: MailDraft) -> MailResult:
        if sys.platform == "win32":
            outlook = self._try_outlook(mail)
            if outlook is not None:
                return outlook
        return self._mailto(mail, send=False)

    async def send(self, mail: MailDraft) -> MailResult:
        # V1: create draft for user to send — never auto-send silently
        result = await self.create_draft(mail)
        if result.ok:
            result.message = "已打开邮件草稿，请确认后手动发送"
        return result

    def _try_outlook(self, mail: MailDraft) -> MailResult | None:
        try:
            import win32com.client  # type: ignore
        except ImportError:
            # try dynamic COM via ctypes-less powershell
            return self._try_outlook_powershell(mail)
        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            item = outlook.CreateItem(0)
            item.To = "; ".join(mail.to)
            if mail.cc:
                item.CC = "; ".join(mail.cc)
            item.Subject = mail.subject
            item.Body = mail.body
            for att in mail.attachments:
                if Path(att).exists():
                    item.Attachments.Add(str(Path(att).resolve()))
            item.Display(True)
            return MailResult(True, "已在 Outlook 中创建草稿", draft_created=True)
        except Exception as exc:  # noqa: BLE001
            logger.info("Outlook COM failed: %s", type(exc).__name__)
            return None

    def _try_outlook_powershell(self, mail: MailDraft) -> MailResult | None:
        atts = ",".join(
            f"'{str(Path(a).resolve())}'" for a in mail.attachments if Path(a).exists()
        )
        to = "; ".join(mail.to).replace("'", "''")
        subject = mail.subject.replace("'", "''")
        body = mail.body.replace("'", "''")
        ps = f"""
$ol = New-Object -ComObject Outlook.Application
$m = $ol.CreateItem(0)
$m.To = '{to}'
$m.Subject = '{subject}'
$m.Body = '{body}'
"""
        if atts:
            ps += f"""
$atts = @({atts})
foreach ($a in $atts) {{ $m.Attachments.Add($a) | Out-Null }}
"""
        ps += "$m.Display()\n"
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if completed.returncode == 0:
                return MailResult(True, "已在 Outlook 中创建草稿", draft_created=True)
        except Exception:  # noqa: BLE001
            pass
        return None

    def _mailto(self, mail: MailDraft, send: bool = False) -> MailResult:
        to = ",".join(mail.to)
        query = {
            "subject": mail.subject,
            "body": mail.body
            + (
                "\n\n[附件请手动添加]\n" + "\n".join(mail.attachments)
                if mail.attachments
                else ""
            ),
        }
        url = f"mailto:{urllib.parse.quote(to)}?{urllib.parse.urlencode(query, quote_via=urllib.parse.quote)}"
        try:
            if sys.platform == "win32":
                os.startfile(url)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", url])
            msg = "已打开系统邮件客户端"
            if mail.attachments:
                msg += "（mailto 无法自动附加文件，请手动添加附件）"
            return MailResult(True, msg, draft_created=True)
        except Exception as exc:  # noqa: BLE001
            return MailResult(False, f"无法打开邮件客户端: {type(exc).__name__}")
