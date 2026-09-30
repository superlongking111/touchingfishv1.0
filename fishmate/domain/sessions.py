"""Big fish / small fish session state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class AppMode(str, Enum):
    SMALL_FISH = "small"
    BIG_FISH = "big"


@dataclass
class BigFishState:
    session_id: int | None = None
    planned_minutes: int | None = None  # None = untimed
    started_at: datetime | None = None
    ends_at: datetime | None = None

    def remaining_seconds(self) -> int | None:
        if self.planned_minutes is None or self.ends_at is None:
            return None
        return max(0, int((self.ends_at - datetime.now()).total_seconds()))

    def is_expired(self) -> bool:
        rem = self.remaining_seconds()
        return rem is not None and rem <= 0

    def extend(self, minutes: int = 5) -> None:
        if self.planned_minutes is None:
            return
        self.planned_minutes += minutes
        if self.ends_at:
            self.ends_at += timedelta(minutes=minutes)
        elif self.started_at:
            self.ends_at = self.started_at + timedelta(minutes=self.planned_minutes)
