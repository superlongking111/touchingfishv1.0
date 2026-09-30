"""Async SHA-256 worker for stable files."""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger("fishmate.hash")


@dataclass
class HashJob:
    event_id: int
    path: str
    max_bytes: int


class HashWorker:
    def __init__(self, on_done: Callable[[int, str], None] | None = None) -> None:
        self._queue: deque[HashJob] = deque()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.on_done = on_done

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="HashWorker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def enqueue(self, event_id: int, path: str, max_bytes: int) -> None:
        with self._lock:
            # replace pending same path
            self._queue = deque(j for j in self._queue if j.path != path)
            self._queue.append(HashJob(event_id, path, max_bytes))

    def _loop(self) -> None:
        while not self._stop.is_set():
            job = None
            with self._lock:
                if self._queue:
                    job = self._queue.popleft()
            if not job:
                time.sleep(0.2)
                continue
            try:
                digest = self._hash_file(job.path, job.max_bytes)
                if digest and self.on_done:
                    self.on_done(job.event_id, digest)
            except Exception as exc:  # noqa: BLE001
                logger.debug("hash failed for %s: %s", job.path, type(exc).__name__)

    @staticmethod
    def _hash_file(path: str, max_bytes: int) -> str | None:
        p = Path(path)
        if not p.is_file():
            return None
        size = p.stat().st_size
        if size > max_bytes:
            logger.info("skip hash, file too large: %s", p.name)
            return None
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def hash_file_sync(path: str | Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
