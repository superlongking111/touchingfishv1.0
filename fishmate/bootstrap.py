"""App bootstrap: paths, logging, single-instance lock."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_DIR_NAME = "FishMate"
MUTEX_NAME = "Local\\FishMate_SingleInstance_V1"


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(base) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return app_data_dir() / "fishmate.db"


def log_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_dir() -> Path:
    path = app_data_dir() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "fishmate"  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent
    return base.joinpath(*parts)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("fishmate")
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = RotatingFileHandler(
        log_dir() / "fishmate.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    # Avoid leaking secrets via third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return logger


class SingleInstance:
    """Windows named mutex single-instance guard."""

    def __init__(self, name: str = MUTEX_NAME) -> None:
        self.name = name
        self._handle = None
        self.already_running = False

    def acquire(self) -> bool:
        if sys.platform != "win32":
            # Non-Windows: file lock fallback
            lock_file = app_data_dir() / "fishmate.lock"
            try:
                fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(fd, str(os.getpid()).encode())
                self._handle = fd
                return True
            except FileExistsError:
                self.already_running = True
                return False

        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.CreateMutexW(None, False, self.name)
        last_error = kernel32.GetLastError()
        ERROR_ALREADY_EXISTS = 183
        self._handle = handle
        if last_error == ERROR_ALREADY_EXISTS:
            self.already_running = True
            return False
        return True

    def release(self) -> None:
        if sys.platform != "win32":
            if self._handle is not None:
                try:
                    os.close(self._handle)
                except OSError:
                    pass
                lock_file = app_data_dir() / "fishmate.lock"
                try:
                    lock_file.unlink(missing_ok=True)
                except OSError:
                    pass
            return
        if self._handle:
            import ctypes

            ctypes.windll.kernel32.CloseHandle(self._handle)  # type: ignore[attr-defined]
            self._handle = None
