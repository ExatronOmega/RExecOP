from __future__ import annotations

import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_public_index_release_smoke.py"
CLEAN_INSTALL = ROOT / "scripts" / "validate_clean_install_smoke.py"
PREFLIGHT = ROOT / "scripts" / "validate_release_train_preflight.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_index_release_smoke_orchestration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _load("rexecop_public_index_release_smoke", SCRIPT)
    clean_install = _load("rexecop_clean_install_smoke", CLEAN_INSTALL)

    class FakeCompleted:
        def __init__(self, *, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    venv = tmp_path / "venv"
    venv.mkdir()
    venv_python = venv / "bin" / "python"
    rexecop_bin = venv / "bin" / "rexecop"
    version = "0.2.24a0"
    marker = clean_install.clean_install_marker(version)
    runtime_root = venv / "runtime"

    def fake_run(command: list[str], *, cwd: Path | None = None) -> FakeCompleted:
        if command[:2] == [str(rexecop_bin), "version"]:
            return FakeCompleted(stdout=f"{version}\n")
        if command[:4] == [str(rexecop_bin), "--root", str(runtime_root), "init"]:
            return FakeCompleted(stdout="ok\n")
        if command[:5] == [str(rexecop_bin), "--json", "--root", str(runtime_root), "doctor"]:
            return FakeCompleted(stdout=json.dumps({"status": "passed", "blockers": []}) + "\n")
        raise AssertionError(f"unexpected_command:{command}")

    @contextmanager
    def fake_install(*_args, **_kwargs):
        yield venv, venv_python, rexecop_bin

    monkeypatch.setattr(clean_install, "isolated_pypi_install", fake_install)
    monkeypatch.setattr(clean_install, "run_surface_smoke", lambda *_a, **_k: marker)
    monkeypatch.setattr(clean_install, "_run", fake_run)

    def fake_load(name: str, path: Path):
        if path == CLEAN_INSTALL:
            return clean_install
        return _load(name, path)

    monkeypatch.setattr(release, "_load_module", fake_load)
    details = release.run_public_index_checks(version, tmp_parent=tmp_path)

    assert details["surface_marker"] == marker
    assert details["version"] == version
    assert details["doctor_status"] == "passed"


def test_public_index_release_smoke_writes_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _load("rexecop_public_index_release_smoke", SCRIPT)
    clean_install = _load("rexecop_clean_install_smoke_current", CLEAN_INSTALL)
    version = clean_install.project_version()
    evidence_dir = tmp_path / "release-evidence"
    monkeypatch.setattr(release, "RELEASE_EVIDENCE_DIR", evidence_dir)

    path = release.write_release_evidence(
        version,
        {
            "surface_marker": f"clean_install_smoke_ok:rexecop=={version}",
            "version": version,
            "doctor_status": "passed",
        },
    )
    text = path.read_text(encoding="utf-8")
    assert f"clean_install_smoke_ok:rexecop=={version}" in text
    assert release.release_marker(version) in text


def test_public_index_release_smoke_cli_success(monkeypatch: pytest.MonkeyPatch) -> None:
    release = _load("rexecop_public_index_release_smoke", SCRIPT)
    version = "0.2.24a0"
    monkeypatch.setattr(
        release,
        "run_public_index_checks",
        lambda *_args, **_kwargs: {
            "surface_marker": f"clean_install_smoke_ok:rexecop=={version}",
            "version": version,
            "doctor_status": "passed",
        },
    )
    assert release.main(["--version", version]) == 0


def test_public_index_release_smoke_verify_post_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _load("rexecop_public_index_release_smoke", SCRIPT)
    clean_install = _load("rexecop_clean_install_smoke_post_publish", CLEAN_INSTALL)
    version = clean_install.project_version()
    evidence_dir = tmp_path / "release-evidence"
    monkeypatch.setattr(release, "RELEASE_EVIDENCE_DIR", evidence_dir)

    def fake_load(name: str, path: Path):
        module = _load(name, path)
        if path == PREFLIGHT:
            module.RELEASE_EVIDENCE_DIR = evidence_dir
        return module

    monkeypatch.setattr(release, "_load_module", fake_load)
    monkeypatch.setattr(
        release,
        "run_public_index_checks",
        lambda *_args, **_kwargs: {
            "surface_marker": f"clean_install_smoke_ok:rexecop=={version}",
            "version": version,
            "doctor_status": "passed",
        },
    )

    assert (
        release.main(
            ["--version", version, "--write-evidence", "--verify-post-publish"],
        )
        == 0
    )
    assert (evidence_dir / f"{version}.md").is_file()
    verified = fake_load("rexecop_validate_release_train_preflight", PREFLIGHT)
    assert verified.collect_errors(post_publish=True, stack_repos={}) == []
