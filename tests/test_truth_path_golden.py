from __future__ import annotations

import json
import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from rexecop.connectors.ssh_readonly import SshReadonlyRuntime
from rexecop.operation.controller import OperationController
from rexecop.operation.state import OperationState
from rexecop.storage.file_store import FileStore
from rexecop.truth_path import TRUTH_PATH_PROJECTION_SCHEMA, project_truth_path

tecrax = pytest.importorskip("tecrax")


@pytest.fixture(autouse=True)
def _fixture_operator_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        SshReadonlyRuntime,
        "_validate_operator_file",
        lambda self, raw_path, *, identity: None,
    )

ROOT = Path(__file__).resolve().parents[1]


def _tecrax_example(path: str) -> Path:
    profile_root = Path(tecrax.profile_root())
    for root in (profile_root.parents[2], profile_root.parents[1]):
        candidate = root / path
        if candidate.is_file():
            return candidate
    return profile_root.parents[2] / path


HOST_INVENTORY_ENVIRONMENT = _tecrax_example(
    "examples/environments/ubuntu-host.readonly.example.yaml"
)
DOCKER_SERVICE_SHOW = (
    "systemctl show docker --property=LoadState --property=ActiveState "
    "--property=SubState --property=UnitFileState --no-pager"
)
DOCKER_SOCKET_SHOW = (
    "systemctl show docker.socket --property=LoadState --property=ActiveState "
    "--property=SubState --property=UnitFileState --no-pager"
)
ADGUARD_DNS_QUERY = (
    "dig @adguard.example.invalid example.com A +time=2 +tries=1 +noall +answer"
)
ADGUARD_LOGIN_STATUS = (
    "curl -q -sS -m 3 --connect-timeout 2 --max-redirs 0 -o /dev/null "
    "-w %{http_code} http://adguard.example.invalid/login.html"
)
AVAILABLE_UPDATES_SUMMARY = "/usr/lib/update-notifier/apt-check"


def _ssh_remote_command(argv: object) -> str:
    if isinstance(argv, list) and argv and str(argv[0]) == "ssh":
        return str(argv[-1])
    text = " ".join(str(item) for item in argv) if isinstance(argv, list) else str(argv)
    marker = " readonly-ssh-user@monitoring-host.example.invalid "
    if marker in text:
        return text.split(marker, 1)[1]
    return text


def _local_command(argv: object) -> str:
    return " ".join(str(item) for item in argv) if isinstance(argv, list) else str(argv)
GOLDEN = ROOT / "tests" / "fixtures" / "truth_path_golden.json"


def _golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


@pytest.mark.delivery
def test_truth_path_golden_matches_tecrax_diagnosis_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    golden = _golden()
    secrets_path = tmp_path / "secrets.yaml"
    secrets_path.write_text(
        "secrets:\n"
        "  monitoring_host_ssh_identity: /tmp/test-identity\n"
        "  portainer_base_url: https://localhost:19443\n"
        "  portainer_ca_file: /tmp/fixture-portainer-ca.pem\n"
    )
    secrets_path.chmod(0o600)
    monkeypatch.setenv("REXECOP_SECRETS_FILE", str(secrets_path))
    outputs = {
        "cat /etc/os-release": 'PRETTY_NAME="Ubuntu 24.04 LTS"\nID=ubuntu\nVERSION_ID="24.04"\n',
        "uname -srm": "Linux 6.8.0 x86_64\n",
        "hostname": "monitoring-host\n",
        "uptime": "up 5 days\n",
        "cat /proc/loadavg": "0.10 0.20 0.30 1/200 12345\n",
        "df -P /": (
            "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
            "/dev/root 100000 9000 91000 9% /\n"
        ),
        "free -m": "Mem: 32000 8000 4000 100 2000 24000\n",
        "timedatectl show --property=NTPSynchronized --property=NTP": (
            "NTP=no\nNTPSynchronized=yes\n"
        ),
        "systemctl is-active ntp": "active\n",
        DOCKER_SERVICE_SHOW: (
            "LoadState=loaded\nActiveState=active\nSubState=running\nUnitFileState=enabled\n"
        ),
        DOCKER_SOCKET_SHOW: (
            "LoadState=loaded\nActiveState=active\nSubState=listening\nUnitFileState=enabled\n"
        ),
        "systemctl is-enabled unattended-upgrades": "enabled\n",
        AVAILABLE_UPDATES_SUMMARY: "0;0\n",
        "sysctl -n kernel.randomize_va_space": "2\n",
        "sysctl -n kernel.dmesg_restrict": "1\n",
        "find /var/run -maxdepth 1 -name reboot-required -printf '%f\\n'": "",
        "ntpq -c 'rv 0 stratum,offset,rootdelay,rootdisp,leap'": (
            "stratum=3, offset=0.123, rootdelay=1.23, rootdisp=2.34, leap=0\n"
        ),
    }
    local_outputs = {
        ADGUARD_DNS_QUERY: (
            "example.com. 300 IN A 104.20.23.154\n"
            "example.com. 300 IN A 172.66.147.243\n"
        ),
        ADGUARD_LOGIN_STATUS: "200",
    }

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        local_command = _local_command(argv)
        if local_command in local_outputs:
            return subprocess.CompletedProcess(argv, 0, local_outputs[local_command], "")
        command = _ssh_remote_command(argv)
        return subprocess.CompletedProcess(argv, 0, outputs[command], "")

    controller = OperationController(store=FileStore(tmp_path / ".rexecop"))
    with (
        patch("rexecop.connectors.ssh_readonly.subprocess.run", side_effect=run),
        patch(
            "rexecop.connectors.http_api.HttpApiConnectorRuntime._open_url",
            side_effect=urllib.error.URLError("unavailable"),
        ),
        patch(
            "rexecop.connectors.http_api.ssl.create_default_context",
            return_value=object(),
        ),
    ):
        operation = controller.plan(
            profile_path="tecrax",
            environment_path=HOST_INVENTORY_ENVIRONMENT,
            intent="diagnose_monitoring_host",
            target="monitoring-host-01",
            mode="dry_run",
            auto_react="plan_only",
        )
        completed = controller.start(operation.id)
        controller.export_receipt(operation.id)

    assert completed.state == OperationState.COMPLETED.value
    stored = controller.get_operation(operation.id)
    plan = controller.store.load_plan(operation.id)
    truth_path = project_truth_path(stored, plan)

    assert truth_path["schema"] == TRUTH_PATH_PROJECTION_SCHEMA
    for section in golden["required_sections"]:
        assert section in truth_path

    observation = truth_path["observation"]
    for key, value in golden["observation"].items():
        assert observation[key] == value
    assert observation["observation_digest"].startswith("sha256:")
    assert observation["facts_digest"].startswith("sha256:")

    auto_reaction = truth_path["auto_reaction"]
    for key, value in golden["auto_reaction"].items():
        assert auto_reaction[key] == value
    assert auto_reaction["chain_root"].startswith("sha256:")
    child_id = auto_reaction["child_operation_id"]
    child = controller.get_operation(child_id)
    assert child.intent == golden["child_intent"]
    assert child.state == OperationState.PLANNED.value

    claim_types = [item["claim_type"] for item in truth_path["evidence_claims"]]
    assert claim_types == golden["evidence_claim_types"]
    assert all(item["result"] == "supported" for item in truth_path["evidence_claims"])

    link_kinds = [item["kind"] for item in truth_path["links"]]
    for kind in golden["required_link_kinds"]:
        assert kind in link_kinds

    governance_trace = truth_path["governance_trace"]
    assert governance_trace["trace_digest"].startswith("sha256:")
    for control in golden["governance_trace_controls"]:
        assert control in governance_trace["required_controls"]

    sclite_roles = {
        item["role"] for item in truth_path["sclite_refs"]["artifacts"] if item.get("digest")
    }
    for role in golden["required_sclite_roles"]:
        assert role in sclite_roles
