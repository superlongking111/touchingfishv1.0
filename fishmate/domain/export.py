"""Export domain types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExportFile:
    path: str
    arcname: str
    size: int
    sha256: str
    mtime: str | None = None
    error: str | None = None


@dataclass
class ExportResult:
    zip_path: str
    zip_sha256: str
    files: list[ExportFile] = field(default_factory=list)
    total_bytes: int = 0
    manifest_path: str | None = None
    ok: bool = True
    error: str | None = None
