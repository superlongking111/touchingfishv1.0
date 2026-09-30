"""Background workers to keep Qt UI responsive."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QThread, Signal

from fishmate.services.content_cycle import ContentCycleReport, run_content_cycle
from fishmate.services.content_fetcher import ContentFetcher
from fishmate.services.llm_client import LLMClient, TestResult
from fishmate.services.mail.base import MailDraft, MailResult
from fishmate.services.mail.factory import smtp_client_from_context
from fishmate.services.mail.smtp_client import SmtpMailClient

if TYPE_CHECKING:
    from fishmate.app_context import AppContext


class LlmTestWorker(QThread):
    finished = Signal(object)  # TestResult
    failed = Signal(str)

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout: float,
    ) -> None:
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def run(self) -> None:
        try:
            client = LLMClient(
                self.base_url,
                self.api_key,
                self.model,
                timeout=self.timeout,
            )
            result = asyncio.run(client.test_connection())
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(type(exc).__name__)


class ContentFetchWorker(QThread):
    finished = Signal(object)  # ContentCycleReport
    failed = Signal(str)

    def __init__(
        self,
        ctx: "AppContext",
        *,
        only_source_id: int | None = None,
        rank: bool = True,
    ) -> None:
        super().__init__()
        self.ctx = ctx
        self.only_source_id = only_source_id
        self.rank = rank

    def run(self) -> None:
        fetcher = ContentFetcher()

        async def _go() -> ContentCycleReport:
            try:
                return await run_content_cycle(
                    self.ctx,
                    fetcher,
                    only_source_id=self.only_source_id,
                    rank=self.rank,
                    push_if_ready=False,
                    respect_daily_limit=False,
                )
            finally:
                await fetcher.close()

        try:
            report = asyncio.run(_go())
            self.finished.emit(report)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(type(exc).__name__)


class MailSendWorker(QThread):
    finished = Signal(object)  # MailResult
    failed = Signal(str)

    def __init__(self, ctx: "AppContext", draft: MailDraft) -> None:
        super().__init__()
        self.ctx = ctx
        self.draft = draft

    def run(self) -> None:
        try:
            client = smtp_client_from_context(self.ctx)
            if client is None:
                self.finished.emit(
                    MailResult(
                        False,
                        "请先在「设置 → 邮件」配置 SMTP 主机、发件邮箱与授权码。",
                    )
                )
                return
            self.finished.emit(client.send_sync(self.draft))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(type(exc).__name__)


class MailTestWorker(QThread):
    finished = Signal(object)  # MailResult
    failed = Signal(str)

    def __init__(self, client: SmtpMailClient, to: str) -> None:
        super().__init__()
        self.client = client
        self.to = to

    def run(self) -> None:
        try:
            draft = MailDraft(
                to=[self.to],
                subject="摸鱼助手 · SMTP 测试",
                body="这是一封测试邮件。收到说明 SMTP 配置正确。",
                attachments=[],
            )
            self.finished.emit(self.client.send_sync(draft))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(type(exc).__name__)
