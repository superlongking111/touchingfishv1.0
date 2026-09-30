"""Path validation for watch roots and ZIP export."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path


class PathPolicy:
    def __init__(self, ignore_patterns: list[str] | None = None) -> None:
        self.ignore_patterns = ignore_patterns or []

    def set_ignore_patterns(self, patterns: list[str]) -> None:
        self.ignore_patterns = list(patterns)

    def should_ignore(self, path: str | Path) -> bool:
        p = Path(path)
        name = p.name
        parts = p.parts
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
            # directory name match
            clean = pattern.strip("*").strip("/").strip("\\")
            if clean and clean in parts:
                return True
        return False

    @staticmethod
    def resolve_real(path: str | Path) -> Path:
        return Path(path).resolve()

    @staticmethod
    def is_under_root(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    def validate_export_files(
        self,
        selected: list[str | Path],
        allowed_roots: list[str | Path] | None = None,
    ) -> list[tuple[Path, str | None]]:
        """Return list of (resolved_path, error_or_None)."""
        results: list[tuple[Path, str | None]] = []
        roots = [Path(r).resolve() for r in (allowed_roots or [])]
        for raw in selected:
            try:
                real = self.resolve_real(raw)
            except OSError:
                results.append((Path(raw), "无法解析路径"))
                continue
            if not real.exists():
                results.append((real, "文件不存在"))
                continue
            if not real.is_file():
                results.append((real, "不是文件"))
                continue
            if roots and not any(self.is_under_root(real, r) for r in roots):
                # Allow explicitly selected files outside roots (user chose them)
                pass
            # Detect symlink escape of parent for packaging relative path
            if real.is_symlink():
                target = real.resolve()
                if roots and not any(self.is_under_root(target, r) for r in roots):
                    results.append((real, "软链接指向未授权路径"))
                    continue
            try:
                with open(real, "rb"):
                    pass
            except OSError:
                results.append((real, "文件被占用或无法读取"))
                continue
            results.append((real, None))
        return results

    @staticmethod
    def safe_arcname(path: Path, used: set[str]) -> str:
        """Build ZIP arcname under files/, avoid collisions."""
        name = path.name
        candidate = f"files/{name}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        stem = path.stem
        suffix = path.suffix
        i = 1
        while True:
            candidate = f"files/{stem}_{i}{suffix}"
            if candidate not in used:
                used.add(candidate)
                return candidate
            i += 1

    @staticmethod
    def relative_arcname(path: Path, root: Path | None, used: set[str]) -> str:
        if root:
            try:
                rel = path.resolve().relative_to(root.resolve())
                candidate = "files/" + rel.as_posix()
                if candidate not in used:
                    used.add(candidate)
                    return candidate
            except ValueError:
                pass
        return PathPolicy.safe_arcname(path, used)
