from __future__ import annotations

import hashlib
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rexecop import __version__
from rexecop.errors import RExecOpValidationError
from rexecop.runtime.init import RUNTIME_DIRECTORIES, RUNTIME_MANIFEST
from rexecop.storage.atomic import atomic_write_text, secure_directory

BACKUP_MANIFEST_SCHEMA = "rexecop.runtime_backup.v0.1"
BACKUP_ARCHIVE_NAME = "runtime_store.tar"
MANIFEST_NAME = "backup_manifest.json"

_SECRET_SCANNER = None


def _secret_scanner():
    global _SECRET_SCANNER
    if _SECRET_SCANNER is None:
        import importlib.util
        import sys

        script = Path(__file__).resolve().parents[3] / "scripts" / "secret_scan.py"
        spec = importlib.util.spec_from_file_location("rexecop_secret_scan", script)
        if spec is None or spec.loader is None:
            raise RExecOpValidationError("secret scan script is unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _SECRET_SCANNER = module
    return _SECRET_SCANNER


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan_runtime_tree(root: Path) -> list[str]:
    scanner = _secret_scanner()
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.endswith(".tmp"):
            continue
        for finding in scanner.scan_path(
            scope="runtime_backup",
            identity=root.name,
            path=str(path),
        ):
            findings.append(finding.render())
    return findings


def create_runtime_backup(
    root: Path,
    *,
    output: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not root.is_dir():
        raise RExecOpValidationError(f"runtime root does not exist: {root}")
    secret_findings = _scan_runtime_tree(root)
    if secret_findings:
        raise RExecOpValidationError(
            "runtime backup blocked by secret scan: " + "; ".join(secret_findings[:5])
        )

    observed_at = now or datetime.now(UTC).replace(microsecond=0)
    secure_directory(output.parent)
    archive_path = output
    if archive_path.suffix not in {".tar", ".tgz", ".tar.gz"}:
        stamp = observed_at.strftime("%Y%m%dT%H%M%SZ")
        archive_path = output / f"rexecop-runtime-backup-{stamp}.tar"
        secure_directory(archive_path.parent)

    files: list[dict[str, str]] = []
    with tarfile.open(archive_path, "w") as archive:
        for relative in _backup_paths(root):
            path = root / relative
            if not path.exists():
                continue
            if path.is_file():
                archive.add(path, arcname=relative, recursive=False)
                files.append(
                    {
                        "path": relative,
                        "sha256": _sha256_file(path),
                    }
                )
            else:
                for child in sorted(path.rglob("*")):
                    if not child.is_file() or child.name.endswith(".tmp"):
                        continue
                    arcname = str(child.relative_to(root))
                    archive.add(child, arcname=arcname, recursive=False)
                    files.append(
                        {
                            "path": arcname,
                            "sha256": _sha256_file(child),
                        }
                    )

    manifest = {
        "schema": BACKUP_MANIFEST_SCHEMA,
        "rexecop_version": __version__,
        "runtime_root_fingerprint": hashlib.sha256(str(root).encode()).hexdigest()[:16],
        "created_at": observed_at.isoformat(),
        "file_count": len(files),
        "files": files,
        "archive": archive_path.name,
    }
    manifest_path = archive_path.with_name(archive_path.stem + ".manifest.json")
    if manifest_path == archive_path:
        manifest_path = archive_path.parent / MANIFEST_NAME
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    return {
        "schema": BACKUP_MANIFEST_SCHEMA,
        "status": "created",
        "archive": str(archive_path),
        "manifest": str(manifest_path),
        "file_count": len(files),
        "secret_scan": "passed",
    }


def restore_runtime_backup(
    *,
    archive: Path,
    target_root: Path,
    manifest: Path | None = None,
) -> dict[str, Any]:
    if not archive.is_file():
        raise RExecOpValidationError(f"backup archive not found: {archive}")
    manifest_path = manifest or archive.with_suffix(".manifest.json")
    if not manifest_path.is_file():
        manifest_path = archive.parent / MANIFEST_NAME
    if not manifest_path.is_file():
        raise RExecOpValidationError("backup manifest is required for restore")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if str(payload.get("schema") or "") != BACKUP_MANIFEST_SCHEMA:
        raise RExecOpValidationError("unsupported backup manifest schema")

    if target_root.exists():
        existing = [path for path in target_root.rglob("*") if path.is_file()]
        allowed = {RUNTIME_MANIFEST}
        unexpected = [
            str(path.relative_to(target_root))
            for path in existing
            if str(path.relative_to(target_root)) not in allowed
        ]
        if unexpected:
            raise RExecOpValidationError(
                "restore requires an empty runtime root; found existing files"
            )

    secure_directory(target_root)
    expected_files = {
        str(item["path"]): str(item["sha256"])
        for item in payload.get("files") or []
        if isinstance(item, dict) and item.get("path") and item.get("sha256")
    }

    with tarfile.open(archive, "r") as archive_handle:
        for member in archive_handle.getmembers():
            if not member.isfile():
                continue
            destination = target_root / member.name
            secure_directory(destination.parent)
            extracted = archive_handle.extractfile(member)
            if extracted is None:
                raise RExecOpValidationError(f"failed to extract backup member: {member.name}")
            data = extracted.read()
            destination.write_bytes(data)
            destination.chmod(0o600)
            expected = expected_files.get(member.name)
            if expected and hashlib.sha256(data).hexdigest() != expected:
                raise RExecOpValidationError(f"backup digest mismatch: {member.name}")

    return {
        "schema": BACKUP_MANIFEST_SCHEMA,
        "status": "restored",
        "target_root": str(target_root),
        "file_count": len(expected_files),
        "manifest": str(manifest_path),
    }


def _backup_paths(root: Path) -> list[str]:
    paths = [RUNTIME_MANIFEST]
    paths.extend(RUNTIME_DIRECTORIES)
    extras = ("reactions", "queue/run_now.json")
    for item in extras:
        if (root / item).exists() and item not in paths:
            paths.append(item)
    return paths