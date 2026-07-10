#!/usr/bin/env python3
"""Install the built wheel in an isolated venv and verify M6/M7/M8 public surfaces."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INSTALLED_SURFACE_SMOKE = """\
import rexecop
from govengine import admit_typed_execution, project_governance_trace
from rexecop.cli_contracts import CLI_CONTRACT_REGISTRY_SCHEMA, cli_contract_registry
from rexecop.cli_errors import CLI_ERROR_SCHEMA
from rexecop.observability.diagnostics import RUNTIME_DIAGNOSTICS_SCHEMA
from rexecop.observability.structured_log import STRUCTURED_LOG_EVENT_SCHEMA
from rexecop.truth_path import project_truth_path

version = {version!r}
assert rexecop.__version__ == version
registry = cli_contract_registry()
assert registry["schema"] == CLI_CONTRACT_REGISTRY_SCHEMA
assert registry["contract_count"] >= 17
assert CLI_ERROR_SCHEMA == "rexecop.cli_error.v0.1"
assert STRUCTURED_LOG_EVENT_SCHEMA == "rexecop.structured_log_event.v0.1"
assert RUNTIME_DIAGNOSTICS_SCHEMA == "rexecop.runtime_diagnostics.v0.1"
assert callable(project_truth_path)
assert callable(admit_typed_execution)
assert callable(project_governance_trace)
print(
    "artifact_install_smoke_ok:"
    f"rexecop=={{version}}:"
    f"contracts={{registry['contract_count']}}:"
    "m6_m7_m8=ok"
)
"""


def _python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def _project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _resolve_wheel(dist_dir: Path) -> Path:
    wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        raise SystemExit(f"artifact_install_smoke_failed:no_wheel:{dist_dir}")
    return wheels[-1]


def _candidate_install_options(candidate_wheel_dirs: Sequence[Path]) -> list[str]:
    options: list[str] = []
    for wheel_dir in candidate_wheel_dirs:
        resolved = wheel_dir.resolve()
        if not resolved.is_dir():
            raise RuntimeError(f"candidate_wheel_dir_missing:{resolved}")
        options.extend(["--find-links", str(resolved)])
    return options


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dist",
        type=Path,
        default=ROOT / "dist",
        help="Directory containing the built wheel.",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Run python -m build before installing the wheel.",
    )
    parser.add_argument(
        "--candidate-wheel-dir",
        action="append",
        type=Path,
        default=[],
        help=(
            "Local wheelhouse used to resolve exact dependency pins before publication; "
            "repeat for multiple directories."
        ),
    )
    args = parser.parse_args()

    version = _project_version()
    python = sys.executable

    if args.build:
        build = _run([python, "-m", "build"], cwd=ROOT)
        if build.returncode != 0:
            print(build.stdout)
            print(build.stderr, file=sys.stderr)
            return build.returncode

    wheel = _resolve_wheel(args.dist)
    with tempfile.TemporaryDirectory(prefix="rexecop-artifact-smoke-") as tmp:
        venv = Path(tmp) / "venv"
        create = _run([python, "-m", "venv", str(venv)], cwd=ROOT)
        if create.returncode != 0:
            print(create.stderr, file=sys.stderr)
            return create.returncode

        venv_python = str(_python(venv))
        try:
            candidate_options = _candidate_install_options(args.candidate_wheel_dir)
        except RuntimeError as exc:
            print(f"artifact_install_smoke_failed:{exc}", file=sys.stderr)
            return 1
        install = _run(
            [
                venv_python,
                "-m",
                "pip",
                "install",
                "-q",
                "--upgrade",
                "pip",
                *candidate_options,
                str(wheel.resolve()),
            ],
            cwd=ROOT,
        )
        if install.returncode != 0:
            print(install.stdout)
            print(install.stderr, file=sys.stderr)
            return install.returncode

        pip_check = _run([venv_python, "-m", "pip", "check"], cwd=ROOT)
        if pip_check.returncode != 0:
            print(pip_check.stdout)
            print(pip_check.stderr, file=sys.stderr)
            return pip_check.returncode

        smoke = _run(
            [
                venv_python,
                "-c",
                INSTALLED_SURFACE_SMOKE.format(version=version),
            ],
            cwd=ROOT,
        )
        if smoke.returncode != 0:
            print(smoke.stdout)
            print(smoke.stderr, file=sys.stderr)
            return smoke.returncode
        print(smoke.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
