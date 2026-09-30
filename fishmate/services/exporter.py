"""ZIP export with manifest and SHA-256."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from fishmate.bootstrap import export_dir
from fishmate.domain.export import ExportFile, ExportResult
from fishmate.security.path_policy import PathPolicy
from fishmate.services.hash_worker import HashWorker


class ExportService:
    def __init__(self, path_policy: PathPolicy | None = None) -> None:
        self.path_policy = path_policy or PathPolicy()

    def build_zip(
        self,
        selected_files: list[str | Path],
        include_worklog: bool = True,
        include_summary: bool = False,
        summary_md: str = "",
        worklog_data: dict | list | None = None,
        zip_name: str | None = None,
        roots: list[str | Path] | None = None,
    ) -> ExportResult:
        checked = self.path_policy.validate_export_files(selected_files)
        errors = [(p, e) for p, e in checked if e]
        ok_files = [p for p, e in checked if e is None]
        if not ok_files and errors:
            return ExportResult(
                zip_path="",
                zip_sha256="",
                ok=False,
                error="; ".join(f"{p.name}:{e}" for p, e in errors),
            )

        day = datetime.now().strftime("%Y-%m-%d")
        zip_name = zip_name or f"{day}_work.zip"
        out_path = export_dir() / zip_name
        # avoid overwrite
        if out_path.exists():
            stem = out_path.stem
            i = 1
            while True:
                candidate = export_dir() / f"{stem}_{i}.zip"
                if not candidate.exists():
                    out_path = candidate
                    break
                i += 1

        used: set[str] = set()
        export_files: list[ExportFile] = []
        root_paths = [Path(r) for r in (roots or [])]

        with tempfile.TemporaryDirectory(prefix="fishmate_export_") as tmp:
            tmp_path = Path(tmp)
            files_dir = tmp_path / "files"
            files_dir.mkdir()

            for src in ok_files:
                root = next((r for r in root_paths if PathPolicy.is_under_root(src, r)), None)
                arc = self.path_policy.relative_arcname(src, root, used)
                dest = tmp_path / arc
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src, dest)
                except OSError as exc:
                    export_files.append(
                        ExportFile(
                            path=str(src),
                            arcname=arc,
                            size=0,
                            sha256="",
                            error=str(type(exc).__name__),
                        )
                    )
                    continue
                digest = HashWorker.hash_file_sync(dest)
                st = dest.stat()
                mtime = datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
                export_files.append(
                    ExportFile(
                        path=str(src),
                        arcname=arc,
                        size=st.st_size,
                        sha256=digest,
                        mtime=mtime,
                    )
                )

            manifest = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "files": [
                    {
                        "arcname": f.arcname,
                        "source_path": f.path,
                        "size": f.size,
                        "sha256": f.sha256,
                        "mtime": f.mtime,
                    }
                    for f in export_files
                    if not f.error
                ],
            }
            (tmp_path / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            if include_worklog:
                (tmp_path / "worklog.json").write_text(
                    json.dumps(worklog_data or [], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            if include_summary and summary_md:
                (tmp_path / "daily_summary.md").write_text(summary_md, encoding="utf-8")

            with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for f in tmp_path.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(tmp_path).as_posix())

        zip_sha = HashWorker.hash_file_sync(out_path)
        total = sum(f.size for f in export_files if not f.error)
        # verify
        self.verify_zip(out_path)
        return ExportResult(
            zip_path=str(out_path),
            zip_sha256=zip_sha,
            files=export_files,
            total_bytes=total,
            ok=True,
        )

    @staticmethod
    def verify_zip(zip_path: str | Path) -> bool:
        zip_path = Path(zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            manifest_raw = zf.read("manifest.json")
            manifest = json.loads(manifest_raw.decode("utf-8"))
            for entry in manifest.get("files", []):
                arc = entry["arcname"]
                expected = entry["sha256"]
                data = zf.read(arc)
                import hashlib

                actual = hashlib.sha256(data).hexdigest()
                if actual != expected:
                    raise ValueError(f"SHA-256 mismatch for {arc}")
        return True
