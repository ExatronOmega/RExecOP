from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_release_train_preflight.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "rexecop_validate_release_train_preflight",
        SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_release_train_preflight_passes(tmp_path: Path) -> None:
    validator = _load_validator()
    public_truth, _ = validator._validator_modules()
    version = public_truth.current_version()
    projects = {
        "govengine": f'''
[project]
name = "govengine"
version = "0.17.0rc1"
dependencies = ["{public_truth.EXPECTED_SCLITE}"]
''',
        "sclite": '''
[project]
name = "sclite-core"
version = "2.0.0"
dependencies = []
''',
        "tecrax": f'''
[project]
name = "tecrax"
version = "0.4.0rc1"
dependencies = [
  "{public_truth.EXPECTED_GOVENGINE}",
  "{public_truth.EXPECTED_SCLITE}",
  "rexecop=={version}",
]
''',
    }
    env = os.environ.copy()
    for name, content in projects.items():
        repo = tmp_path / name
        repo.mkdir()
        (repo / "pyproject.toml").write_text(content, encoding="utf-8")
        env[validator._STACK_REPO_ENV[name]] = str(repo)
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    assert result.stdout.strip() == validator.success_line(
        version,
        post_publish=False,
        govengine=public_truth.EXPECTED_GOVENGINE,
        sclite=public_truth.EXPECTED_SCLITE,
        tecrax=public_truth.EXPECTED_TECRAX_EXTRA,
    )


def test_release_train_preflight_rejects_validator_constant_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _load_validator()
    public_truth, stack_contracts = validator._validator_modules()
    monkeypatch.setattr(stack_contracts, "EXPECTED_GOVENGINE", "govengine==9.9.9")
    errors = validator.collect_errors(stack_repos={})
    assert any(
        error.startswith("validator_constant_mismatch:EXPECTED_GOVENGINE:")
        for error in errors
    )


def test_release_train_preflight_rejects_tecrax_pin_drift(tmp_path: Path) -> None:
    validator = _load_validator()
    public_truth, _ = validator._validator_modules()
    tecrax_root = tmp_path / "tecrax"
    tecrax_root.mkdir()
    (tecrax_root / "pyproject.toml").write_text(
        """
[project]
name = "tecrax"
version = "0.3.21a0"
dependencies = [
  "govengine==0.16.11",
  "sclite-core==1.0.9",
  "rexecop==9.9.9a0",
]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    errors = validator.collect_errors(stack_repos={"tecrax": tecrax_root})
    assert any("tecrax_repo_rexecop_pin_mismatch" in item for item in errors)


def test_release_train_preflight_rejects_sclite_repo_version_drift(tmp_path: Path) -> None:
    validator = _load_validator()
    sclite_root = tmp_path / "sclite"
    sclite_root.mkdir()
    (sclite_root / "pyproject.toml").write_text(
        '''
[project]
name = "sclite-core"
version = "2.0.0rc1"
dependencies = []
'''.strip()
        + "\n",
        encoding="utf-8",
    )
    errors = validator.collect_errors(stack_repos={"sclite": sclite_root})
    assert "sclite_repo_version_mismatch:2.0.0rc1!=2.0.0" in errors


def test_release_train_preflight_rejects_missing_sibling_repos() -> None:
    validator = _load_validator()
    errors = validator.collect_errors(stack_repos={})
    assert "sibling_repo_missing:govengine" in errors
    assert "sibling_repo_missing:sclite" in errors
    assert "sibling_repo_missing:tecrax" in errors


def test_release_train_preflight_post_publish_requires_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _load_validator()
    monkeypatch.setattr(validator, "_has_post_publish_evidence", lambda _version: False)
    errors = validator.collect_errors(post_publish=True, stack_repos={})
    assert any(error.startswith("post_publish_evidence_missing:") for error in errors)


def test_release_train_preflight_post_publish_accepts_changelog_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _load_validator()
    version = validator._validator_modules()[0].current_version()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    marker = validator._release_evidence_marker(version)
    if marker not in validator._changelog_section(ROOT / "CHANGELOG.md", version):
        changelog = changelog.replace(
            f"## [{version}]",
            f"## [{version}]\n\n- Release evidence: `{marker}`\n",
            1,
        )

    def fake_changelog_section(path: Path, current_version: str) -> str:
        if path.name == "CHANGELOG.md" and current_version == version:
            _, _, tail = changelog.partition(f"## [{version}]")
            return tail
        return validator._changelog_section(path, current_version)

    monkeypatch.setattr(validator, "_changelog_section", fake_changelog_section)
    errors = validator.collect_errors(post_publish=True, stack_repos={})
    assert not any(error.startswith("post_publish_evidence_missing:") for error in errors)
