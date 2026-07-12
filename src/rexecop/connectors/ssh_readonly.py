from __future__ import annotations

import shlex
import stat
import subprocess
from pathlib import Path
from typing import Any

from rexecop.connectors import errors as connector_errors
from rexecop.connectors.base import (
    ConnectorRequest,
    ConnectorResponse,
    effective_output_bytes,
    effective_timeout_seconds,
)
from rexecop.connectors.command_shape import normalize_allowlisted_argv
from rexecop.connectors.errors import READ_ONLY_MODES
from rexecop.errors import RExecOpValidationError
from rexecop.evidence.redaction import redact_payload, redact_text, register_secret_value
from rexecop.execution.output import bounded_text
from rexecop.secrets.port import SecretResolver
from rexecop.secrets.resolver import default_secret_resolver

ALLOWED_KNOWN_HOSTS_POLICIES = frozenset({"accept-new", "strict", "no"})


class SshReadonlyRuntime:
    """Temporary read-only SSH connector — allowlisted remote commands only.

    Full remote-command policy is enforced by GovEngine PolicyEngine when
    `environment.policy_pack` is configured; allowlisted argv remains a
    second-layer safety check in this connector.
    """

    def __init__(
        self,
        *,
        connector_name: str,
        config: dict[str, Any],
        secret_resolver: SecretResolver | None = None,
    ) -> None:
        self.connector_name = connector_name
        self.config = config
        self.secret_resolver = secret_resolver or default_secret_resolver()

    def invoke(self, request: ConnectorRequest) -> ConnectorResponse:
        if request.connector != self.connector_name:
            return ConnectorResponse(
                connector=request.connector,
                action=request.action,
                success=False,
                error="connector mismatch",
                data={"error_class": connector_errors.UNSUPPORTED},
            )
        if request.mode not in READ_ONLY_MODES:
            return ConnectorResponse(
                connector=request.connector,
                action=request.action,
                success=False,
                error="ssh_readonly refuses mutating operation modes",
                data={"error_class": connector_errors.POLICY_DENIED},
            )
        allowlist = self.config.get("allowlist")
        if not isinstance(allowlist, list):
            return ConnectorResponse(
                connector=request.connector,
                action=request.action,
                success=False,
                error="allowlist missing",
                data={"error_class": connector_errors.VALIDATION_FAILED},
            )
        entry = self._find_allowlist_entry(allowlist, request.action)
        if entry is None:
            return ConnectorResponse(
                connector=request.connector,
                action=request.action,
                success=False,
                error="command not allowlisted",
                data={"error_class": connector_errors.CAPABILITY_UNDECLARED},
            )
        try:
            remote_command = self._build_remote_command(allowlist, entry)
            argv = self._build_ssh_argv(remote_command)
        except (RExecOpValidationError, ValueError) as exc:
            return ConnectorResponse(
                connector=request.connector,
                action=request.action,
                success=False,
                error=str(exc),
                data={"error_class": connector_errors.VALIDATION_FAILED},
            )
        timeout = effective_timeout_seconds(
            request,
            float(self.config.get("timeout_seconds") or 15),
        )
        try:
            completed = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ConnectorResponse(
                connector=request.connector,
                action=request.action,
                success=False,
                error="ssh command timeout",
                data={"error_class": connector_errors.TIMEOUT},
            )
        success = completed.returncode == 0
        max_output_bytes = effective_output_bytes(
            request,
            int(self.config.get("max_output_bytes") or 65536),
        )
        stdout = bounded_text(completed.stdout, max_bytes=max_output_bytes)
        stderr = bounded_text(completed.stderr, max_bytes=max_output_bytes)
        return ConnectorResponse(
            connector=request.connector,
            action=request.action,
            success=success,
            data=redact_payload(
                {
                    "stdout": stdout.text,
                    "stderr": stderr.text,
                    "returncode": completed.returncode,
                    "remote_command": remote_command,
                    "output_digests": {
                        "stdout": stdout.digest,
                        "stderr": stderr.digest,
                    },
                    "output_truncated": {
                        "stdout": stdout.truncated,
                        "stderr": stderr.truncated,
                    },
                    "output_sizes": {
                        "stdout_bytes": stdout.original_bytes,
                        "stderr_bytes": stderr.original_bytes,
                    },
                }
            ),
            error="" if success else redact_text(completed.stderr.strip()) or "ssh command failed",
        )

    def _build_remote_command(
        self,
        allowlist: list[Any],
        entry: dict[str, Any],
    ) -> str:
        allowed_tools = {
            str(item.get("command")).strip().lower()
            for item in allowlist
            if isinstance(item, dict) and str(item.get("command") or "").strip()
        }
        tool = str(entry.get("command") or "").strip()
        args = entry.get("args") or []
        if not isinstance(args, list):
            raise RExecOpValidationError("ssh allowlist args must be a list")
        argv = normalize_allowlisted_argv(tool=tool, args=args, allowed_tools=allowed_tools)
        return " ".join(shlex.quote(part) for part in argv)

    def _build_ssh_argv(self, remote_command: str) -> list[str]:
        host = str(self.config.get("host") or "").strip()
        user = str(self.config.get("user") or "").strip()
        if not host or not user:
            raise RExecOpValidationError("ssh_readonly requires host and user")
        self._validate_destination(host=host, user=user)
        posture = str(self.config.get("deployment_posture") or "stable").strip().lower()
        policy = str(self.config.get("known_hosts_policy") or "strict").strip()
        if policy not in ALLOWED_KNOWN_HOSTS_POLICIES:
            raise RExecOpValidationError(
                f"unsupported known_hosts_policy: {policy}"
            )
        if posture not in {"stable", "lab", "fixture"}:
            raise RExecOpValidationError(f"unsupported deployment_posture: {posture}")
        if posture == "stable" and policy != "strict":
            raise RExecOpValidationError(
                "stable ssh_readonly requires strict known-host verification"
            )
        ssh_policy = "yes" if policy == "strict" else policy
        argv = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"StrictHostKeyChecking={ssh_policy}",
        ]
        known_hosts_file = str(self.config.get("known_hosts_file") or "").strip()
        if policy == "strict" and not known_hosts_file:
            raise RExecOpValidationError(
                "strict ssh_readonly requires known_hosts_file"
            )
        if known_hosts_file:
            self._validate_operator_file(known_hosts_file, identity=False)
            argv.extend(["-o", f"UserKnownHostsFile={known_hosts_file}"])
        port = self.config.get("port")
        if port is not None:
            try:
                normalized_port = int(port)
            except (TypeError, ValueError) as exc:
                raise RExecOpValidationError("ssh port must be an integer") from exc
            if not 1 <= normalized_port <= 65535:
                raise RExecOpValidationError("ssh port is outside 1..65535")
            argv.extend(["-p", str(normalized_port)])
        identity_ref = str(self.config.get("identity_file_secret_ref") or "").strip()
        if identity_ref:
            identity_file = self.secret_resolver.resolve(identity_ref)
            register_secret_value(identity_file)
            self._validate_operator_file(identity_file, identity=True)
            argv.extend(["-i", identity_file])
        argv.append(f"{user}@{host}")
        argv.append(remote_command)
        return argv

    @staticmethod
    def _validate_destination(*, host: str, user: str) -> None:
        for label, value in (("host", host), ("user", user)):
            if value.startswith("-") or any(char.isspace() for char in value):
                raise RExecOpValidationError(f"ssh {label} is malformed")
            if any(char in value for char in {"@", "\x00", "/", "\\"}):
                raise RExecOpValidationError(f"ssh {label} is malformed")

    def _validate_operator_file(self, raw_path: str, *, identity: bool) -> None:
        path = Path(raw_path)
        try:
            info = path.lstat()
        except OSError as exc:
            raise RExecOpValidationError("ssh operator file is unavailable") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise RExecOpValidationError("ssh operator file must be a regular non-symlink")
        if info.st_uid != Path.home().stat().st_uid:
            raise RExecOpValidationError("ssh operator file has unexpected owner")
        forbidden = 0o077 if identity else 0o022
        if info.st_mode & forbidden:
            kind = "identity" if identity else "known_hosts"
            raise RExecOpValidationError(f"ssh {kind} file permissions are too broad")

    def _find_allowlist_entry(
        self,
        allowlist: list[Any],
        action: str,
    ) -> dict[str, Any] | None:
        for item in allowlist:
            if not isinstance(item, dict):
                continue
            if str(item.get("action") or item.get("command")) == action:
                return item
        return None
