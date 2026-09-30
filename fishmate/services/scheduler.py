"""Central scheduler: reminders, content fetch, retention."""

from __future__ import annotations

import asyncio
import logging
import random
import threading
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable

from apscheduler.schedulers.background import BackgroundScheduler

from fishmate.domain.reminders import ReminderPlanner
from fishmate.services.content_cycle import run_content_cycle
from fishmate.services.content_fetcher import ContentFetcher
from fishmate.services.notifier import is_fullscreen_app_active

if TYPE_CHECKING:
    from fishmate.app_context import AppContext

logger = logging.getLogger("fishmate.scheduler")


class AppScheduler:
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx
        self.planner = ReminderPlanner()
        self.fetcher = ContentFetcher()
        self._scheduler = BackgroundScheduler()
        self._next_content_at: datetime | None = None
        self._deferred_reminders: list[int] = []
        self.on_reminder: Callable | None = None
        self.on_content: Callable | None = None
        self.in_big_fish = False
        self._content_job_running = False

    def enter_big_fish_mode(self) -> None:
        """摸大鱼开着 → 小摸鱼提醒冻结（含再摸 5 分钟，只要未关窗就一直冻）。"""
        self.in_big_fish = True
        self.planner.freeze_timers()

    def exit_big_fish_mode(self) -> None:
        """关闭摸大鱼 → 小摸鱼从冻结时的剩余时间继续倒计时。"""
        self.in_big_fish = False
        self.planner.resume_timers_after_freeze()

    def start(self) -> None:
        self.planner.reset()
        reminders = self.ctx.reminders.list_enabled()
        self.planner.ensure_scheduled(reminders)
        self._schedule_next_content()
        # Reminder/content ticks run on Qt GUI thread (see FishMateApp QTimer).
        self._scheduler.add_job(
            self._retention,
            "cron",
            hour=3,
            minute=15,
            id="retention",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("scheduler started")

    def stop(self) -> None:
        try:
            self._scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass
        try:
            asyncio.run(self.fetcher.close())
        except Exception:  # noqa: BLE001
            pass

    def on_system_resume(self) -> None:
        self.planner.on_resume_from_sleep()
        reminders = self.ctx.reminders.list_enabled()
        self.planner.ensure_scheduled(reminders)
        self._schedule_next_content()
        logger.info("rescheduled after resume")

    def resume_fish_timers(self) -> None:
        """After「开启摸鱼」— reschedule reminders and content fetch from now."""
        self.planner.reset()
        self.planner.ensure_scheduled(self.ctx.reminders.list_enabled())
        self._schedule_next_content()

    def reload_reminders(self) -> None:
        """After settings change — re-read DB and schedule from now."""
        self.planner.reschedule_all_enabled(self.ctx.reminders.list_enabled())
        logger.info("reminders rescheduled from settings")

    def _fish_paused(self) -> bool:
        return bool(self.ctx.settings.get("fish_paused"))

    def _paused_until(self) -> datetime | None:
        raw = self.ctx.settings.get("reminders_paused_until")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def run_main_thread_tick(self) -> None:
        """Must be invoked from the Qt main thread (QTimer)."""
        try:
            if self._fish_paused():
                return
            self._tick_reminders()
            self._start_content_job_if_due()
        except Exception:  # noqa: BLE001
            logger.exception("scheduler tick failed")

    def _start_content_job_if_due(self) -> None:
        if self._content_job_running:
            return
        if self._next_content_at is None:
            self._schedule_next_content()
            return
        if datetime.now() < self._next_content_at:
            return
        self._schedule_next_content()
        self._content_job_running = True

        def worker() -> None:
            try:
                asyncio.run(self._content_job())
            except Exception:  # noqa: BLE001
                logger.exception("content job failed")
            finally:
                self._content_job_running = False

        threading.Thread(target=worker, name="fishmate-content", daemon=True).start()

    def _tick_reminders(self) -> None:
        reminders = self.ctx.reminders.list_enabled()
        self.planner.ensure_scheduled(reminders)
        defer = bool(self.ctx.settings.get("defer_when_fullscreen", True))
        fullscreen = defer and is_fullscreen_app_active()
        due = self.planner.due_now(
            reminders,
            paused_until=self._paused_until(),
            in_big_fish=self.in_big_fish,
        )
        for item in due:
            if fullscreen:
                self.planner.acknowledge(item.reminder, "timeout")
                continue
            if self.on_reminder:
                self.on_reminder(item.reminder)

    def _schedule_next_content(self) -> None:
        lo = int(self.ctx.settings.get("content_fetch_min_minutes", 35))
        hi = int(self.ctx.settings.get("content_fetch_max_minutes", 90))
        if hi < lo:
            hi = lo
        mins = random.randint(lo, hi)
        self._next_content_at = datetime.now() + timedelta(minutes=mins)

    async def _content_job(self) -> None:
        def on_push(item: object) -> bool:
            if self.on_content:
                self.on_content(item)
            return False

        await run_content_cycle(
            self.ctx,
            self.fetcher,
            push_if_ready=True,
            on_push=on_push,
            in_big_fish=self.in_big_fish,
        )

    def fetch_now(self) -> None:
        self._next_content_at = datetime.now()

    async def run_content_now(self):
        return await run_content_cycle(
            self.ctx,
            self.fetcher,
            push_if_ready=False,
            respect_daily_limit=False,
        )

    def _retention(self) -> None:
        days = int(self.ctx.settings.get("data_retention_days", 90))
        dedupe_days = int(self.ctx.settings.get("content_dedupe_days", 7))
        self.ctx.content.purge_older_than(max(days, dedupe_days))
        self.ctx.worklog.purge_older_than(days)
        logger.info("retention job done")
