from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class MailDraft:
    to: list[str]
    subject: str
    body: str
    attachments: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)


@dataclass
class MailResult:
    ok: bool
    message: str
    draft_created: bool = False


class MailAdapter(Protocol):
    async def create_draft(self, mail: MailDraft) -> MailResult: ...
    async def send(self, mail: MailDraft) -> MailResult: ...
