#!/usr/bin/env python3
"""Verify a clean PyPI install of rexecop[tecrax] exposes M6/M7/M8 surfaces."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import tomllib
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
assert CLI_ERROR_SCHEMA == "rexecop.cli_error.v0.1"
assert STRUCTURED_LOG_EVENT_SCHEMA == "rexecop.structured_log_event.v0.1"
assert RUNTIME_DIAGNOSTICS_SCHEMA == "rexecop.runtime_diagnostics.v0.1"
assert callable(project_truth_path)
assert callable(admit_typed_execution)
assert callable(project_governance_trace)
print(
    "clean_install_smoke_ok:"
    f"rexecop=={{version}}:"
    f"contracts={{registry['contract_count']}}:"
    "pip_check=ok"
)
"""


def _python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(command, text=True, capture_output=True, check=False, env=env)


def _project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version",
        default="",
        help="Package version to install (defaults to pyproject version).",
    )
    parser.add_argument(
        "--no-tecrax-extra",
        action="store_true",
        help="Install rexecop without the tecrax extra.",
    )
    args = parser.parse_args()

    version = args.version or _project_version()
    requirement = f"rexecop=={version}" if args.no_tecrax_extra else f"rexecop[tecrax]=={version}"
    python = sys.executable

    with tempfile.TemporaryDirectory(prefix="rexecop-clean-install-") as tmp:
        venv = Path(tmp) / "venv"
        create = _run([python, "-m", "venv", str(venv)])
        if create.returncode != 0:
            print(create.stderr, file=sys.stderr)
            return create.returncode

        venv_python = str(_python(venv))
        install = _run(
            [
                venv_python,
                "-m",
                "pip",
                "install",
                "-q",
                "--upgrade",
                "pip",
                "--pre",
                requirement,
            ]
        )
        if install.returncode != 0:
            print(install.stdout)
            print(install.stderr, file=sys.stderr)
            return install.returncode

        pip_check = _run([venv_python, "-m", "pip", "check"])
        if pip_check.returncode != 0:
            print(pip_check.stdout)
            print(pip_check.stderr, file=sys.stderr)
            return pip_check.returncode

        smoke = _run(
            [
                venv_python,
                "-c",
                INSTALLED_SURFACE_SMOKE.format(version=version),
            ]
        )
        if smoke.returncode != 0:
            print(smoke.stdout)
            print(smoke.stderr, file=sys.stderr)
            return smoke.returncode
        print(smoke.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())