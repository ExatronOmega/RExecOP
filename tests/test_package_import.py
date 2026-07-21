from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import rexecop

ROOT = Path(__file__).resolve().parents[1]


def package_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_package_import() -> None:
    assert rexecop.__version__


def test_version_matches_pyproject() -> None:
    assert rexecop.__version__ == package_version()


def test_declared_runtime_modules_import_in_fresh_subprocess() -> None:
    modules = (
        "rexecop.runtime_ops.lease",
        "rexecop.runtime_ops.queue",
        "rexecop.runtime_ops.attempts",
        "rexecop.runtime_ops.permit",
        "rexecop.storage.port",
        "rexecop.storage.file_store",
    )
    for module in modules:
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_legacy_lazy_package_exports_remain_cycle_safe() -> None:
    from rexecop.operation import Operation, OperationController
    from rexecop.runtime_ops import RunNowQueue, RuntimeCoordinator
    from rexecop.storage import FileStore, create_store

    assert all(
        item is not None
        for item in (
            Operation,
            OperationController,
            RunNowQueue,
            RuntimeCoordinator,
            FileStore,
            create_store,
        )
    )
