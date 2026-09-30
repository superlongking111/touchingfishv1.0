"""Marshal scheduler callbacks onto the Qt GUI thread."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from fishmate.repositories.reminder_repo import Reminder


class SchedulerUiBridge(QObject):
    """Background threads must not create Qt widgets — queue work on the GUI thread."""

    reminder_due = Signal(object)
    content_push = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._reminder_handler: Callable[["Reminder"], None] | None = None
        self._content_handler: Callable[[object], bool] | None = None
        self.reminder_due.connect(self._dispatch_reminder)
        self.content_push.connect(self._dispatch_content)

    def bind(
        self,
        on_reminder: Callable[["Reminder"], None],
        on_content: Callable[[object], bool],
    ) -> None:
        self._reminder_handler = on_reminder
        self._content_handler = on_content

    def emit_reminder(self, reminder: "Reminder") -> None:
        self.reminder_due.emit(reminder)

    def queue_content_push(self, item: object) -> None:
        """From worker thread; handler runs on GUI thread."""
        self.content_push.emit(item)

    def _dispatch_reminder(self, reminder: object) -> None:
        if self._reminder_handler:
            self._reminder_handler(reminder)  # type: ignore[arg-type]

    def _dispatch_content(self, item: object) -> None:
        if self._content_handler:
            self._content_handler(item)
