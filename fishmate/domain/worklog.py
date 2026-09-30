"""Worklog helpers: aggregation for daily report input."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from fishmate.repositories.worklog_repo import FileEvent


@dataclass
class AggregatedFile:
    path: str
    types: list[str]
    first_time: str
    last_time: str
    count: int


def aggregate_events(events: list[FileEvent]) -> list[AggregatedFile]:
    groups: dict[str, list[FileEvent]] = defaultdict(list)
    for e in events:
        groups[e.path].append(e)
    result: list[AggregatedFile] = []
    for path, items in groups.items():
        items_sorted = sorted(items, key=lambda x: x.event_time)
        types = []
        for it in items_sorted:
            if it.event_type not in types:
                types.append(it.event_type)
        result.append(
            AggregatedFile(
                path=path,
                types=types,
                first_time=items_sorted[0].event_time,
                last_time=items_sorted[-1].event_time,
                count=len(items_sorted),
            )
        )
    result.sort(key=lambda x: x.last_time)
    return result


def events_to_llm_payload(events: list[FileEvent], notes: str, date: str) -> dict:
    compact = []
    for e in events:
        # Prefer relative-looking short path for LLM
        path = e.path.replace("\\", "/")
        if "/" in path:
            path = "/".join(path.split("/")[-3:])
        compact.append(
            {
                "time": e.event_time[11:16] if len(e.event_time) >= 16 else e.event_time,
                "type": e.event_type,
                "path": path,
            }
        )
    return {"date": date, "events": compact, "user_notes": notes}
