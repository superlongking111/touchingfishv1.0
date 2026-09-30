"""Watchdog-based work directory watcher with debounce."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from fishmate.repositories.worklog_repo import WorklogRepo
from fishmate.security.path_policy import PathPolicy

logger = logging.getLogger("fishmate.watcher")


class _Handler(FileSystemEventHandler):
    def __init__(self, service: "FileWatchService", root_id: int, root_path: str) -> None:
        super().__init__()
        self.service = service
        self.root_id = root_id
        self.root_path = root_path

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self.service._handle(self.root_id, "CREATE", event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self.service._handle(self.root_id, "MODIFY", event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self.service._handle(self.root_id, "DELETE", event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        dest = getattr(event, "dest_path", None)
        self.service._handle(self.root_id, "RENAME", dest or event.src_path, old_path=event.src_path)


class FileWatchService:
    def __init__(
        self,
        worklog: WorklogRepo,
        path_policy: PathPolicy,
        debounce_seconds: int = 5,
        hash_max_bytes: int = 2 * 1024**3,
        on_stable_file: Callable[[int, str], None] | None = None,
    ) -> None:
        self.worklog = worklog
        self.path_policy = path_policy
        self.debounce_seconds = debounce_seconds
        self.hash_max_bytes = hash_max_bytes
        self.on_stable_file = on_stable_file
        self._observer: Observer | None = None
        self._lock = threading.Lock()
        self._pending_modify: dict[str, tuple[int, float]] = {}
        self._flush_stop = threading.Event()
        self._flush_thread: threading.Thread | None = None

    def start(self) -> None:
        self.stop()
        self._observer = Observer()
        roots = self.worklog.list_roots(enabled_only=True)
        for root in roots:
            p = Path(root.path)
            if not p.exists() or not p.is_dir():
                logger.warning("watch root missing: %s", root.path)
                continue
            handler = _Handler(self, root.id, root.path)
            self._observer.schedule(handler, root.path, recursive=root.recursive)
            logger.info("watching %s", root.path)
        self._observer.start()
        self._flush_stop.clear()
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def stop(self) -> None:
        self._flush_stop.set()
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=3)
            except Exception:  # noqa: BLE001
                pass
            self._observer = None

    def reload(self) -> None:
        self.start()

    def _handle(
        self,
        root_id: int,
        event_type: str,
        path: str,
        old_path: str | None = None,
    ) -> None:
        if self.path_policy.should_ignore(path):
            return
        if old_path and self.path_policy.should_ignore(old_path):
            return
        if event_type == "MODIFY":
            with self._lock:
                self._pending_modify[path] = (root_id, time.time())
            return
        self._record(root_id, event_type, path, old_path)

    def _flush_loop(self) -> None:
        while not self._flush_stop.is_set():
            time.sleep(0.5)
            now = time.time()
            ready: list[tuple[int, str]] = []
            with self._lock:
                for path, (root_id, ts) in list(self._pending_modify.items()):
                    if now - ts >= self.debounce_seconds:
                        ready.append((root_id, path))
                        del self._pending_modify[path]
            for root_id, path in ready:
                self._record(root_id, "MODIFY", path)

    def _record(
        self,
        root_id: int,
        event_type: str,
        path: str,
        old_path: str | None = None,
    ) -> None:
        size = None
        mtime = None
        p = Path(path) if path else None
        if p and p.exists() and p.is_file():
            try:
                st = p.stat()
                size = st.st_size
                mtime = datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
            except OSError:
                pass

        if event_type == "MODIFY":
            existing = self.worklog.recent_modify(path, self.debounce_seconds + 1)
            if existing:
                self.worklog.update_event_meta(
                    existing.id,
                    size,
                    mtime,
                    datetime.now().isoformat(timespec="seconds"),
                )
                event_id = existing.id
            else:
                event_id = self.worklog.insert_event(
                    root_id, event_type, path, old_path, size, mtime
                )
        else:
            event_id = self.worklog.insert_event(
                root_id, event_type, path, old_path, size, mtime
            )

        if (
            event_type in ("CREATE", "MODIFY", "RENAME")
            and p
            and p.exists()
            and p.is_file()
            and self.on_stable_file
        ):
            self.on_stable_file(event_id, str(p))
