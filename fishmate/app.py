"""FishMate application entrypoint."""

from __future__ import annotations

import logging
import sys
from collections import deque
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QTimer

from fishmate.ui.ui_bridge import SchedulerUiBridge
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from fishmate import APP_NAME, __version__
from fishmate.app_context import AppContext
from fishmate.bootstrap import SingleInstance, db_path, setup_logging
from fishmate.domain.reminders import PRIMARY_ACTIONS
from fishmate.domain.sessions import AppMode, BigFishState
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
from fishmate.services.file_watcher import FileWatchService
from fishmate.services.hash_worker import HashWorker
from fishmate.services.scheduler import AppScheduler
from fishmate.ui.big_fish_window import BigFishWindow, DurationDialog
from fishmate.ui.export_wizard import ExportWizard
from fishmate.ui.onboarding import OnboardingDialog
from fishmate.ui.settings_window import SettingsWindow
from fishmate.ui.timeline_window import TimelineWindow
from fishmate.ui.app_icon import app_icon, apply_window_icon
from fishmate.ui.tray import TrayController
from fishmate.ui.widgets.content_toast import ContentFishToast
from fishmate.ui.widgets.toast import ToastNotification
from fishmate.ui.style import apply_app_theme, apply_readable_theme


logger = logging.getLogger("fishmate.app")


class FishMateApp:
    def __init__(self) -> None:
        self.qt = QApplication.instance() or QApplication(sys.argv)
        self.qt.setApplicationName(APP_NAME)
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setStyle("Fusion")
        ic = app_icon()
        if not ic.isNull():
            self.qt.setWindowIcon(ic)

        self.db = Database(db_path())
        self.db.migrate()
        settings = SettingsRepo(self.db)
        settings.ensure_defaults()
        apply_app_theme(self.qt, str(settings.get("ui_theme") or "light"))
        reminders = ReminderRepo(self.db)
        reminders.seed_defaults()
        content = ContentRepo(self.db)
        content.seed_defaults()
        preset_rev = int(settings.get("content_preset_revision") or 0)
        if preset_rev < 3:
            content.remove_non_default_presets()
            content.ensure_default_sources()
            settings.set("content_preset_revision", 3)
        else:
            content.ensure_default_sources()
        worklog = WorklogRepo(self.db)
        sessions = SessionRepo(self.db)
        exports = ExportRepo(self.db)
        secrets = SecretStore()
        path_policy = PathPolicy(settings.get("ignore_patterns") or [])

        self.hash_worker = HashWorker(on_done=self._on_hash_done)
        self.ctx = AppContext(
            db=self.db,
            settings=settings,
            reminders=reminders,
            content=content,
            worklog=worklog,
            sessions=sessions,
            exports=exports,
            secrets=secrets,
            path_policy=path_policy,
            hash_worker=self.hash_worker,
        )

        self.mode = AppMode.SMALL_FISH
        self.big_state = BigFishState()
        self.big_window: BigFishWindow | None = None
        self.settings_window: SettingsWindow | None = None
        self._toasts: list[ToastNotification] = []
        self._reminder_queue: deque = deque()
        self._reminder_toast_open = False
        self._content_toast: ContentFishToast | None = None

        self.watcher = FileWatchService(
            worklog,
            path_policy,
            debounce_seconds=int(settings.get("modify_debounce_seconds", 5)),
            hash_max_bytes=int(settings.get("hash_max_bytes", 2 * 1024**3)),
            on_stable_file=self._enqueue_hash,
        )
        self._tray_host = QWidget()
        self._tray_host.setWindowTitle(APP_NAME)
        self.tray = TrayController(
            parent=self._tray_host,
            on_open_big_fish=self.open_big_fish,
            on_settings=self.open_settings,
            on_toggle_pause=self.toggle_fish_pause,
            on_quit=self.quit,
            icon=ic,
        )
        if bool(self.ctx.settings.get("fish_paused")):
            self.tray.set_fish_paused(True)
        apply_window_icon(self._tray_host)

        self.scheduler = AppScheduler(self.ctx)
        self._ui_bridge = SchedulerUiBridge(self._tray_host)
        self._ui_bridge.bind(self._on_reminder, self._on_content)
        self.scheduler.on_reminder = self._ui_bridge.emit_reminder
        self.scheduler.on_content = self._ui_bridge.queue_content_push
        self._sched_timer = QTimer(self._tray_host)
        self._sched_timer.timeout.connect(self.scheduler.run_main_thread_tick)
        self._sched_timer.start(1000)

        # Power resume poll (lightweight)
        self._power_timer = QTimer()
        self._power_timer.timeout.connect(self._check_resume)
        self._power_timer.start(30_000)
        self._last_tick = datetime.now()

        if not settings.get("onboarding_done"):
            OnboardingDialog(self.ctx).exec()

        self.hash_worker.start()
        self.watcher.start()
        self.scheduler.start()
        logger.info("FishMate %s started (small fish)", __version__)

    def _enqueue_hash(self, event_id: int, path: str) -> None:
        self.hash_worker.enqueue(
            event_id,
            path,
            int(self.ctx.settings.get("hash_max_bytes", 2 * 1024**3)),
        )

    def _on_hash_done(self, event_id: int, digest: str) -> None:
        self.ctx.worklog.update_sha256(event_id, digest)

    def toggle_fish_pause(self) -> None:
        paused = bool(self.ctx.settings.get("fish_paused"))
        if not paused:
            self.ctx.settings.set("fish_paused", True)
            self.ctx.settings.set("reminders_paused_until", None)
            if self._content_toast and self._content_toast.isVisible():
                self._content_toast.close()
            self.tray.set_fish_paused(True)
            self.tray.show_message("摸鱼助手", "已暂停：提醒与内容推送均停止。")
            return
        self.ctx.settings.set("fish_paused", False)
        self.scheduler.resume_fish_timers()
        self.tray.set_fish_paused(False)
        self.tray.show_message("摸鱼助手", "已开启：计时已从当前重新安排。")

    def _check_resume(self) -> None:
        now = datetime.now()
        if now - self._last_tick > timedelta(minutes=3):
            self.scheduler.on_system_resume()
        self._last_tick = now

    def _clear_reminder_toasts(self) -> None:
        self._reminder_queue.clear()
        for toast in list(self._toasts):
            toast.blockSignals(True)
            toast.close()
        self._toasts.clear()
        self._reminder_toast_open = False

    def _on_reminder(self, reminder) -> None:
        if self.scheduler.in_big_fish or self.scheduler.planner.is_frozen():
            return
        self._reminder_queue.append(reminder)
        self._pump_reminder_queue()

    def _pump_reminder_queue(self) -> None:
        if self._reminder_toast_open or not self._reminder_queue:
            return
        if self.scheduler.in_big_fish or self.scheduler.planner.is_frozen():
            self._reminder_queue.clear()
            return
        reminder = self._reminder_queue.popleft()
        self._reminder_toast_open = True
        event_id = self.ctx.reminders.log_event(reminder.id, "shown")
        fade = int(self.ctx.settings.get("notification_fade_seconds", 10))
        primary = PRIMARY_ACTIONS.get(reminder.type, "好的")
        snooze_min = int(self.ctx.settings.get("reminder_snooze_minutes", 10))

        def on_primary() -> None:
            self.ctx.reminders.update_event_action(event_id, "primary")
            if reminder.type == "rest":
                pass

        def on_snooze() -> None:
            self.ctx.reminders.update_event_action(event_id, "snooze")

        theme = str(self.ctx.settings.get("ui_theme") or "light")
        toast = ToastNotification(
            title=reminder.name,
            body=reminder.message,
            primary_text=primary,
            snooze_text=f"稍后 {snooze_min} 分钟",
            fade_seconds=fade,
            on_primary=on_primary,
            on_snooze=on_snooze,
            parent=self._tray_host,
            theme=theme,
        )

        def on_closed(action: str) -> None:
            if action == "dismiss":
                self.ctx.reminders.update_event_action(event_id, "dismiss")
            elif action == "timeout":
                self.ctx.reminders.update_event_action(event_id, "timeout")
            if action == "snooze":
                self.scheduler.planner.acknowledge(
                    reminder, "snooze", snooze_min
                )
            else:
                self.scheduler.planner.acknowledge(reminder, action)
            if toast in self._toasts:
                self._toasts.remove(toast)
            self._reminder_toast_open = False
            self._pump_reminder_queue()

        toast.closed.connect(on_closed)
        self._toasts.append(toast)
        toast.show()
        toast.raise_()

    def _on_content(self, item) -> bool:
        """Show one content toast; return False if a toast is already open (skip auto-push)."""
        if self.scheduler.in_big_fish:
            return False
        if self._content_toast and self._content_toast.isVisible():
            return False
        fade = int(self.ctx.settings.get("notification_fade_seconds", 10))
        toast = ContentFishToast(
            self.ctx,
            item,
            fade_seconds=fade,
            on_open_big=self.open_big_fish,
            parent=self._tray_host,
        )
        self._content_toast = toast

        def on_closed(_action: str) -> None:
            if self._content_toast is toast:
                self._content_toast = None

        toast.closed.connect(on_closed)
        toast.show()
        self.ctx.content.set_status(item.id, "pushed")
        return True

    def open_big_fish(self) -> None:
        if self.mode == AppMode.BIG_FISH and self.big_window:
            self.big_window.raise_()
            self.big_window.activateWindow()
            return
        theme = str(self.ctx.settings.get("ui_theme") or "light")
        dlg = DurationDialog(theme=theme)
        if dlg.exec() != DurationDialog.DialogCode.Accepted:
            return
        minutes = dlg.minutes
        session_id = self.ctx.sessions.start("big", minutes)
        started = datetime.now()
        ends = started + timedelta(minutes=minutes) if minutes is not None else None
        self.big_state = BigFishState(
            session_id=session_id,
            planned_minutes=minutes,
            started_at=started,
            ends_at=ends,
        )
        self.mode = AppMode.BIG_FISH
        self._clear_reminder_toasts()
        if self._content_toast and self._content_toast.isVisible():
            self._content_toast.close()
        self.scheduler.enter_big_fish_mode()
        self.tray.set_mode(True)
        self.big_window = BigFishWindow(
            self.ctx,
            self.big_state,
            on_ended=self._end_big_fish,
        )
        self.big_window.request_timeline.connect(self.open_timeline)
        self.big_window.request_export.connect(self.open_export)
        self.big_window.request_settings.connect(self.open_settings)
        self.big_window.show()

    def _end_big_fish(self, reason: str) -> None:
        if self.big_state.session_id:
            self.ctx.sessions.end(self.big_state.session_id, reason)
        self.mode = AppMode.SMALL_FISH
        self.scheduler.exit_big_fish_mode()
        self.tray.set_mode(False)
        self.big_window = None
        self.big_state = BigFishState()
        logger.info("returned to small fish (%s)", reason)

    def _raise_visible_toasts(self) -> None:
        for t in self._toasts:
            if t.isVisible():
                t.raise_()
        if self._content_toast and self._content_toast.isVisible():
            self._content_toast.raise_()

    def open_settings(self) -> None:
        def on_changed(flags: dict) -> None:
            if flags.get("theme_changed"):
                theme = str(self.ctx.settings.get("ui_theme") or "light")
                apply_app_theme(self.qt, theme)
                if self.big_window:
                    self.big_window.apply_ui_theme(theme)
                if self._content_toast:
                    self._content_toast.apply_ui_theme(theme)
                for t in self._toasts:
                    t.apply_ui_theme(theme)
            if flags.get("reload_watch") or flags.get("saved"):
                self.watcher.debounce_seconds = int(
                    self.ctx.settings.get("modify_debounce_seconds", 5)
                )
                self.watcher.hash_max_bytes = int(
                    self.ctx.settings.get("hash_max_bytes", 2 * 1024**3)
                )
                self.ctx.refresh_path_policy()
                self.watcher.reload()
            if flags.get("fetch_now"):
                self.scheduler.fetch_now()
            if flags.get("reminders_changed"):
                self.scheduler.reload_reminders()

        if self.settings_window and self.settings_window.isVisible():
            self.settings_window.raise_()
            self.settings_window.activateWindow()
            self._raise_visible_toasts()
            return

        dlg = SettingsWindow(self.ctx, on_changed=on_changed, parent=self._tray_host)
        dlg.setWindowModality(Qt.WindowModality.NonModal)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dlg.finished.connect(lambda _code: setattr(self, "settings_window", None))
        self.settings_window = dlg
        dlg.show()
        self._raise_visible_toasts()

    def open_timeline(self) -> None:
        TimelineWindow(self.ctx).exec()

    def open_export(self) -> None:
        summary = ""
        if self.big_window and hasattr(self.big_window, "_last_summary"):
            summary = getattr(self.big_window, "_last_summary", "") or ""
        ExportWizard(self.ctx, summary_md=summary).exec()

    def quit(self) -> None:
        logger.info("quitting")
        open_sess = self.ctx.sessions.get_open()
        if open_sess:
            self.ctx.sessions.end(open_sess.id, "quit")
        self.scheduler.stop()
        self.watcher.stop()
        self.hash_worker.stop()
        self.db.close()
        self.qt.quit()

    def run(self) -> int:
        return self.qt.exec()


def main() -> int:
    setup_logging()
    lock = SingleInstance()
    if not lock.acquire():
        # Second instance: try to inform user
        app = QApplication.instance() or QApplication(sys.argv)
        ic = app_icon()
        if not ic.isNull():
            app.setWindowIcon(ic)
        box = QMessageBox()
        box.setWindowTitle(APP_NAME)
        box.setText("摸鱼助手已在运行，请从系统托盘打开。")
        if not ic.isNull():
            box.setWindowIcon(ic)
        box.setIcon(QMessageBox.Icon.Information)
        box.exec()
        return 0
    try:
        app = FishMateApp()
        code = app.run()
    finally:
        lock.release()
    return code


if __name__ == "__main__":
    sys.exit(main())
