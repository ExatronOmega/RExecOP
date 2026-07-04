from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from rexecop.errors import RExecOpValidationError
from rexecop.execution.executor import StepExecutor
from rexecop.execution.typed_spec import (
    COMMAND_EXECUTION_SPEC_SCHEMA,
    HTTP_ACTION_EXECUTION_SPEC_SCHEMA,
    STATIC_FIXTURE_EXECUTION_SPEC_SCHEMA,
    STEP_EXECUTION_SPEC_SCHEMA,
    bind_step_execution_spec,
    compile_step_execution_spec,
    step_execution_spec_digest,
    validate_typed_execution_schema_version,
)
from rexecop.profile.loader import load_profile
from rexecop.workflow.runner import WorkflowRunner

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PROFILE = ROOT / "examples/profiles/runtime-fixture/profile.yaml"
FIXTURE_ENV = ROOT / "examples/environments/runtime-fixture.example.yaml"


def test_compile_static_fixture_step_execution_spec() -> None:
    env = yaml.safe_load(FIXTURE_ENV.read_text(encoding="utf-8"))
    profile = load_profile(FIXTURE_PROFILE)
    step = {
        "id": "inspect_state",
        "type": "connector",
        "connector": "fixture_source",
        "action": "read_fixture_state",
    }

    spec = compile_step_execution_spec(
        step=step,
        profile=profile,
        connector_config=env["environment"]["connectors"]["fixture_source"],
        mode="dry_run",
    )

    assert spec["schema"] == STEP_EXECUTION_SPEC_SCHEMA
    assert spec["projection_kind"] == "runtime_projection"
    assert spec["digest"].startswith("sha256:")
    assert spec["payload"]["schema"] == STATIC_FIXTURE_EXECUTION_SPEC_SCHEMA
    assert "not a SCLite truth artifact" in spec["non_claims"][0]


def test_compile_http_action_execution_spec_from_fixture(tmp_path: Path) -> None:
    profile_root = tmp_path / "profile"
    (profile_root / "connectors").mkdir(parents=True)
    (profile_root / "intents").mkdir()
    (profile_root / "workflows").mkdir()
    (profile_root / "validation_rules").mkdir()
    (profile_root / "profile.yaml").write_text(
        yaml.safe_dump(
            {
                "profile_contract": {
                    "name": "http_typed_spec",
                    "version": "0.1.0",
                    "intents": {"required": True},
                    "workflows": {"required": True},
                    "connector_requirements": {"required": True},
                    "risk_classes": {"required": True},
                    "evidence_requirements": {"required": True},
                    "governance_expectations": {"required": True},
                    "validation_rules": {"required": True},
                    "escalation_rules": {"required": True},
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (profile_root / "connectors" / "api.yaml").write_text(
        yaml.safe_dump(
            {
                "connector": {
                    "name": "api",
                    "backend": "http_api",
                    "capabilities": ["read_state"],
                    "action_shapes": {
                        "read_state": {
                            "method": "GET",
                            "path": "/state",
                            "unwrap": "state",
                            "max_response_bytes": 2048,
                        }
                    },
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    connector_config = {
        "enabled": True,
        "backend": "http_api",
        "actions": {
            "read_state": {
                "method": "GET",
                "path": "/state",
                "unwrap": "state",
                "max_response_bytes": 2048,
            }
        },
    }
    profile = load_profile(profile_root / "profile.yaml")
    step = {
        "id": "read",
        "type": "connector",
        "connector": "api",
        "action": "read_state",
    }

    spec = compile_step_execution_spec(
        step=step,
        profile=profile,
        connector_config=connector_config,
        mode="dry_run",
    )

    assert spec["payload"]["schema"] == HTTP_ACTION_EXECUTION_SPEC_SCHEMA
    assert spec["payload"]["shape_digest"].startswith("sha256:")
    assert spec["payload"]["shape"]["method"] == "GET"


def test_compile_command_execution_spec_for_readonly_shell(tmp_path: Path) -> None:
    profile_root = tmp_path / "profile"
    (profile_root / "connectors").mkdir(parents=True)
    (profile_root / "intents").mkdir()
    (profile_root / "workflows").mkdir()
    (profile_root / "validation_rules").mkdir()
    (profile_root / "profile.yaml").write_text(
        yaml.safe_dump(
            {
                "profile_contract": {
                    "name": "shell_typed_spec",
                    "version": "0.1.0",
                    "intents": {"required": True},
                    "workflows": {"required": True},
                    "connector_requirements": {"required": True},
                    "risk_classes": {"required": True},
                    "evidence_requirements": {"required": True},
                    "governance_expectations": {"required": True},
                    "validation_rules": {"required": True},
                    "escalation_rules": {"required": True},
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (profile_root / "connectors" / "host.yaml").write_text(
        yaml.safe_dump(
            {
                "connector": {
                    "name": "host",
                    "backend": "local_shell_readonly",
                    "capabilities": ["uptime"],
                    "command_shapes": {
                        "uptime": {"command": "uptime", "args": ["-p"]}
                    },
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    connector_config = {
        "enabled": True,
        "backend": "local_shell_readonly",
        "allowlist": [{"action": "uptime", "command": "uptime", "args": ["-p"]}],
        "max_output_bytes": 4096,
    }
    profile = load_profile(profile_root / "profile.yaml")
    step = {
        "id": "uptime",
        "type": "connector",
        "connector": "host",
        "action": "uptime",
    }

    spec = compile_step_execution_spec(
        step=step,
        profile=profile,
        connector_config=connector_config,
        mode="dry_run",
    )

    assert spec["payload"]["schema"] == COMMAND_EXECUTION_SPEC_SCHEMA
    assert spec["payload"]["argv"] == ["uptime", "-p"]
    assert spec["payload"]["argv_digest"].startswith("sha256:")


def test_step_execution_spec_digest_is_canonical_and_deterministic() -> None:
    env = yaml.safe_load(FIXTURE_ENV.read_text(encoding="utf-8"))
    profile = load_profile(FIXTURE_PROFILE)
    step = {
        "id": "inspect_state",
        "type": "connector",
        "connector": "fixture_source",
        "action": "read_fixture_state",
    }
    kwargs = {
        "step": step,
        "profile": profile,
        "connector_config": env["environment"]["connectors"]["fixture_source"],
        "mode": "dry_run",
    }

    first = compile_step_execution_spec(**kwargs)
    second = compile_step_execution_spec(**kwargs)

    assert first["digest"] == second["digest"]
    assert first["digest"] == step_execution_spec_digest(first)


def test_unknown_typed_execution_schema_major_version_fail_closed() -> None:
    spec = {
        "schema": STEP_EXECUTION_SPEC_SCHEMA,
        "schema_version": "v9.0",
    }

    with pytest.raises(RExecOpValidationError, match="unsupported typed execution schema major"):
        validate_typed_execution_schema_version(spec)


def test_bind_step_execution_spec_detects_drift() -> None:
    env = yaml.safe_load(FIXTURE_ENV.read_text(encoding="utf-8"))
    profile = load_profile(FIXTURE_PROFILE)
    step = {
        "id": "inspect_state",
        "type": "connector",
        "connector": "fixture_source",
        "action": "read_fixture_state",
    }
    spec = compile_step_execution_spec(
        step=step,
        profile=profile,
        connector_config=env["environment"]["connectors"]["fixture_source"],
        mode="dry_run",
    )
    shared_state: dict[str, object] = {}
    bind_step_execution_spec(step_id="inspect_state", spec=spec, shared_state=shared_state)

    drifted = dict(spec)
    drifted["action"] = "mutated_action"
    drifted["digest"] = step_execution_spec_digest(drifted)

    with pytest.raises(RExecOpValidationError, match="typed execution spec drift"):
        bind_step_execution_spec(
            step_id="inspect_state",
            spec=drifted,
            shared_state=shared_state,
        )


def test_workflow_runner_binds_typed_execution_spec_for_fixture_connector() -> None:
    from rexecop.connectors.runtime import ConnectorDispatcher
    from rexecop.connectors.static_fixture import StaticFixtureRuntime

    runtime = StaticFixtureRuntime(
        connector_name="fixture_source",
        mutating_allowed=False,
        config={
            "fixture_only": True,
            "actions": {
                "read_fixture_state": {"data": {"observed": True}},
            },
        },
    )
    executor = StepExecutor(connector_dispatcher=ConnectorDispatcher(runtime))
    env = yaml.safe_load(FIXTURE_ENV.read_text(encoding="utf-8"))
    shared_state = {
        "execution_context": {
            "profile_root": str(FIXTURE_PROFILE),
            "connectors": env["environment"]["connectors"],
        }
    }

    with patch("rexecop.connectors.http_api.urllib.request.urlopen") as backend:
        result = WorkflowRunner(executor).run(
            operation_id="op-typed-spec",
            target="fixture-target",
            mode="dry_run",
            planned_steps=[
                {
                    "id": "inspect_state",
                    "type": "connector",
                    "connector": "fixture_source",
                    "action": "read_fixture_state",
                }
            ],
            correlation_id="corr-typed-spec",
            shared_state=shared_state,
        )

    backend.assert_not_called()
    assert result.success
    typed_specs = result.shared_state["typed_execution_specs"]
    assert typed_specs["inspect_state"]["digest"].startswith("sha256:")
    assert typed_specs["inspect_state"]["schema"] == STEP_EXECUTION_SPEC_SCHEMA