from __future__ import annotations

import pytest

from rexecop.runtime.doctor import _check_executor_posture, _check_storage_backend

pytestmark = pytest.mark.m9_runtime


def test_file_store_is_stable_single_host_certified() -> None:
    check = _check_storage_backend("file")

    assert check["status"] == "passed"
    assert check["details"]["certification_tier"] == "stable_single_host"
    assert check["details"]["single_executor"] is True
    assert check["details"]["multi_executor"] is False


def test_sqlite_is_supported_but_blocked_for_stable_runtime() -> None:
    check = _check_storage_backend("sqlite")

    assert check["status"] == "blocker"
    assert check["details"]["certification_tier"] == "alpha_single_host"


def test_doctor_blocks_multi_executor_posture() -> None:
    check = _check_executor_posture("multi_worker")

    assert check["status"] == "blocker"
    assert check["details"]["certified"] == "single_executor"


def test_doctor_accepts_single_executor_posture() -> None:
    check = _check_executor_posture("single_executor")

    assert check["status"] == "passed"
