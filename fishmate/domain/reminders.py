"""Reminder scheduling domain."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import Callable

from fishmate.repositories.reminder_repo import Reminder


@dataclass
class DueReminder:
    reminder: Reminder
    fire_at: datetime


class ReminderPlanner:
    def __init__(self) -> None:
        self._next_fire: dict[int, datetime] = {}
        self._snoozed_until: dict[int, datetime] = {}
        self._awaiting_ack: set[int] = set()
        self._frozen: bool = False
        self._frozen_remaining: dict[int, timedelta] = {}

    def reset(self) -> None:
        self._next_fire.clear()
        self._snoozed_until.clear()
        self._awaiting_ack.clear()
        self._frozen = False
        self._frozen_remaining.clear()

    def is_frozen(self) -> bool:
        return self._frozen

    def freeze_timers(self, now: datetime | None = None) -> None:
        """摸大鱼窗口打开期间：小摸鱼提醒暂停；关闭窗口后从剩余时间继续。"""
        now = now or datetime.now()
        self._frozen = True
        self._awaiting_ack.clear()
        self._frozen_remaining.clear()
        for rid, fire_at in list(self._next_fire.items()):
            rem = fire_at - now
            if rem.total_seconds() < 0:
                rem = timedelta(0)
            self._frozen_remaining[rid] = rem

    def resume_timers_after_freeze(self, now: datetime | None = None) -> None:
        now = now or datetime.now()
        if not self._frozen:
            return
        for rid, rem in self._frozen_remaining.items():
            self._next_fire[rid] = now + rem
        self._frozen_remaining.clear()
        self._frozen = False
        self._awaiting_ack.clear()

    def on_resume_from_sleep(self) -> None:
        """Recompute next fires; do not backfill missed reminders."""
        now = datetime.now()
        for rid, fire_at in list(self._next_fire.items()):
            if fire_at < now:
                # push to future recompute on next schedule call
                del self._next_fire[rid]

    def reschedule(self, reminder: Reminder, from_time: datetime | None = None) -> datetime:
        """Apply current DB settings — next fire from from_time (default now)."""
        return self.schedule_next(reminder, from_time)

    def reschedule_all_enabled(self, reminders: list[Reminder]) -> None:
        now = datetime.now()
        enabled_ids = {r.id for r in reminders if r.enabled}
        for rid in list(self._next_fire):
            if rid not in enabled_ids:
                del self._next_fire[rid]
        for r in reminders:
            if r.enabled:
                self.schedule_next(r, now)

    def schedule_next(self, reminder: Reminder, from_time: datetime | None = None) -> datetime:
        now = from_time or datetime.now()
        if reminder.schedule_type == "fixed":
            nxt = self._next_fixed(reminder, now)
        else:
            interval = max(1, reminder.interval_minutes or 45)
            jitter = reminder.jitter_minutes or 0
            delta = interval
            if jitter > 0:
                delta = max(1, interval + random.randint(-jitter, jitter))
            nxt = now + timedelta(minutes=delta)
        nxt = self._clamp_to_window(reminder, nxt)
        self._next_fire[reminder.id] = nxt
        return nxt

    def ensure_scheduled(self, reminders: list[Reminder]) -> None:
        if self._frozen:
            return
        now = datetime.now()
        for r in reminders:
            if not r.enabled:
                self._next_fire.pop(r.id, None)
                continue
            if r.id not in self._next_fire:
                self.schedule_next(r, now)

    def due_now(
        self,
        reminders: list[Reminder],
        now: datetime | None = None,
        paused_until: datetime | None = None,
        in_big_fish: bool = False,
    ) -> list[DueReminder]:
        now = now or datetime.now()
        if paused_until and now < paused_until:
            return []
        if in_big_fish or self._frozen:
            return []
        result: list[DueReminder] = []
        enabled = {r.id: r for r in reminders if r.enabled}
        for rid, fire_at in list(self._next_fire.items()):
            if rid not in enabled:
                continue
            if fire_at > now:
                continue
            r = enabled[rid]
            snooze_until = self._snoozed_until.get(rid)
            if snooze_until and now < snooze_until:
                if self._next_fire.get(rid, now) < snooze_until:
                    self._next_fire[rid] = snooze_until
                continue
            if snooze_until and now >= snooze_until:
                self._snoozed_until.pop(rid, None)
            if rid in self._awaiting_ack:
                continue
            if self._in_active_window(r, now):
                result.append(DueReminder(r, fire_at))
                self._awaiting_ack.add(rid)
                return result
            self.schedule_next(r, now)
        return result

    def acknowledge(
        self,
        reminder: Reminder,
        action: str,
        snooze_minutes: int = 10,
        from_time: datetime | None = None,
    ) -> None:
        """After popup closes: snooze silences this reminder globally; else advance schedule."""
        now = from_time or datetime.now()
        rid = reminder.id
        self._awaiting_ack.discard(rid)
        if action == "snooze":
            until = now + timedelta(minutes=snooze_minutes)
            self._snoozed_until[rid] = until
            self._next_fire[rid] = until
            return
        self._snoozed_until.pop(rid, None)
        self.schedule_next(reminder, now)

    def snooze(self, reminder_id: int, minutes: int = 10) -> None:
        until = datetime.now() + timedelta(minutes=minutes)
        self._snoozed_until[reminder_id] = until
        self._next_fire[reminder_id] = until

    def next_fire_map(self) -> dict[int, datetime]:
        return dict(self._next_fire)

    @staticmethod
    def _parse_hhmm(value: str) -> time:
        parts = value.split(":")
        return time(int(parts[0]), int(parts[1]))

    def _in_active_window(self, reminder: Reminder, now: datetime) -> bool:
        window = reminder.active_window or {}
        start_s = window.get("start", "00:00")
        end_s = window.get("end", "23:59")
        start_t = self._parse_hhmm(start_s)
        end_t = self._parse_hhmm(end_s)
        t = now.time().replace(second=0, microsecond=0)
        if start_t <= end_t:
            return start_t <= t <= end_t
        return t >= start_t or t <= end_t

    def _clamp_to_window(self, reminder: Reminder, when: datetime) -> datetime:
        if self._in_active_window(reminder, when):
            return when
        window = reminder.active_window or {}
        start_t = self._parse_hhmm(window.get("start", "09:00"))
        # move to next day's start
        candidate = datetime.combine(when.date(), start_t)
        if candidate <= when:
            candidate += timedelta(days=1)
        return candidate

    def _next_fixed(self, reminder: Reminder, now: datetime) -> datetime:
        times = sorted(reminder.fixed_times or [])
        if not times:
            return now + timedelta(hours=24)
        today = now.date()
        candidates: list[datetime] = []
        for ts in times:
            t = self._parse_hhmm(ts)
            candidates.append(datetime.combine(today, t))
            candidates.append(datetime.combine(today + timedelta(days=1), t))
        future = [c for c in candidates if c > now]
        return min(future) if future else now + timedelta(days=1)


PRIMARY_ACTIONS = {
    "water": "我去接水",
    "walk": "走两分钟",
    "rest": "休息 5 分钟",
    "toilet": "出发",
    "content": "瞅一眼",
    "big_fish_end": "结束摸大鱼",
    "custom": "好的",
}
