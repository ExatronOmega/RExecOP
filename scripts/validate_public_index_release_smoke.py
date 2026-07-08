#!/usr/bin/env python3
"""Post-publish public-index release gate for rexecop[tecrax] on PyPI.

Runs clean PyPI install smoke, CLI version/doctor checks, optional release
evidence recording, and emits a release-train marker for preflight --post-publish.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_EVIDENCE_DIR = ROOT / "docs" / "release-evidence"

_CLEAN_INSTALL = ROOT / "scripts" / "validate_clean_install_smoke.py"
_PREFLIGHT = ROOT / "scripts" / "validate_release_train_preflight.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable_to_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_cli_json(command: list[str], *, cwd: Path) -> dict:
    clean_install = _load_module("rexecop_validate_clean_install_smoke", _CLEAN_INSTALL)
    result = clean_install._run(command, cwd=cwd)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "cli_failed"
        raise RuntimeError(f"{' '.join(command)}:{message}")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{' '.join(command)}:expected_json_object")
    return payload


def run_public_index_checks(
    version: str,
    *,
    no_tecrax_extra: bool = False,
    tmp_parent: Path | None = None,
) -> dict[str, str]:
    clean_install = _load_module("rexecop_validate_clean_install_smoke", _CLEAN_INSTALL)
    with clean_install.isolated_pypi_install(
        version,
        no_tecrax_extra=no_tecrax_extra,
        tmp_parent=tmp_parent,
    ) as (venv, venv_python, rexecop_bin):
        surface_marker = clean_install.run_surface_smoke(venv_python, version)

        version_result = clean_install._run([str(rexecop_bin), "version"], cwd=venv)
        if version_result.returncode != 0:
            raise RuntimeError(version_result.stderr.strip() or "rexecop_version_failed")
        reported_version = version_result.stdout.strip()
        if reported_version != version:
            raise RuntimeError(f"rexecop_version_mismatch:{reported_version}!={version}")

        runtime_root = venv / "runtime"
        init_result = clean_install._run(
            [str(rexecop_bin), "--root", str(runtime_root), "init"],
            cwd=venv,
        )
        if init_result.returncode != 0:
            raise RuntimeError(init_result.stderr.strip() or "rexecop_init_failed")

        doctor = _run_cli_json(
            [str(rexecop_bin), "--json", "--root", str(runtime_root), "doctor"],
            cwd=venv,
        )
        if doctor.get("status") == "blocker":
            raise RuntimeError(f"rexecop_doctor_blocker:{','.join(doctor.get('blockers') or [])}")

    return {
        "surface_marker": surface_marker,
        "version": reported_version,
        "doctor_status": str(doctor.get("status", "")),
    }


def release_marker(version: str) -> str:
    clean_install_marker = f"clean_install_smoke_ok:rexecop=={version}"
    return f"public_index_release_smoke_ok:rexecop=={version}:{clean_install_marker}"


def write_release_evidence(version: str, details: dict[str, str]) -> Path:
    RELEASE_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = RELEASE_EVIDENCE_DIR / f"{version}.md"
    clean_install = _load_module("rexecop_validate_clean_install_smoke", _CLEAN_INSTALL)
    marker = clean_install.clean_install_marker(version)
    lines = [
        f"# Release evidence — rexecop {version}",
        "",
        f"Recorded: {datetime.now(UTC).isoformat()}",
        "",
        "## Public-index smoke",
        "",
        f"`{marker}`",
        "",
        f"`{release_marker(version)}`",
        "",
        f"- rexecop version: `{details['version']}`",
        f"- doctor status: `{details['doctor_status']}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def collect_errors(*, version: str, post_publish: bool) -> list[str]:
    if not post_publish:
        return []
    preflight = _load_module("rexecop_validate_release_train_preflight", _PREFLIGHT)
    return preflight.collect_errors(post_publish=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Public-index release smoke gate for rexecop.")
    parser.add_argument("--version", default="", help="Published version (defaults to pyproject).")
    parser.add_argument("--no-tecrax-extra", action="store_true")
    parser.add_argument(
        "--write-evidence",
        action="store_true",
        help="Write docs/release-evidence/<version>.md with smoke markers.",
    )
    parser.add_argument(
        "--verify-post-publish",
        action="store_true",
        help="After smoke/evidence, run validate_release_train_preflight.py --post-publish.",
    )
    args = parser.parse_args(argv)

    clean_install = _load_module("rexecop_validate_clean_install_smoke", _CLEAN_INSTALL)
    version = args.version or clean_install.project_version()
    try:
        details = run_public_index_checks(version, no_tecrax_extra=args.no_tecrax_extra)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.write_evidence:
        evidence_path = write_release_evidence(version, details)
        print(f"release_evidence_written:{evidence_path}", flush=True)

    if args.verify_post_publish:
        errors = collect_errors(version=version, post_publish=True)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1

    print(release_marker(version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
