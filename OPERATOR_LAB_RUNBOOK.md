# Operator lab runbook (Phase 11–15)

RExecOp `0.2.0a0` — validate neutral core, plugin boundaries, read-only paths, and the full
profile → GovEngine → SCLite emission path before apply.

## Prerequisites

| Item | Command / check |
|------|-----------------|
| Python 3.11+ | `python --version` |
| RExecOp | `pip install -e ".[dev]"` from repo root (see [docs/distribution.md](docs/distribution.md)) |
| Tecrax (domain plugins) | `pip install -e ../tecrax` |
| GovEngine / SCLite | Installed via rexecop dependencies |
| Secrets file | `~/.rexecop/secrets.yaml` mode `0600` |

```bash
export REXECOP_SECRETS_FILE=~/.rexecop/secrets.yaml
rexecop version    # 0.2.0a0
export REXECOP_STORAGE=sqlite   # optional Phase 13.1 backend
python scripts/validate_public_truth.py
```

## Lab checklist

### 1. Core boundary

- [ ] `python scripts/validate_public_truth.py` passes
- [ ] `ruff check . --exclude tecrax` passes
- [ ] `rg 'vm-101|proxmox|pbs|zabbix' src/rexecop` returns **no matches**
- [ ] `rg 'import tecrax' src/rexecop` returns **no matches**

### 2. Secrets hygiene

- [ ] No plaintext tokens in git or committed `.rexecop/`
- [ ] Environment YAML uses `secret_ref` / `base_url_secret_ref` only
- [ ] After a run: `rg -i 'api_key|token|password' .rexecop/` shows only `[REDACTED]` or no hits

### 3. http_api-only golden path (no domain internals)

Uses `examples/profiles/http-health-fixture` — single connector step, no Tecrax internal actions.

```bash
pytest tests/test_http_health_check_e2e.py -q
```

Manual path: copy a staging env with `backend: http_api` pointing at your `/health` endpoint.

- [ ] `plan` + `start` → `completed`
- [ ] `validate` → `passed: true`, rule `http_health_check.probe_ok`

### 4. Tecrax offline fixture (bootstrap)

Requires `tecrax` installed (`rexecop.internal_actions` + `tecrax_fixture` mock).

```bash
rexecop plan \
  --profile examples/profiles/tecrax-fixture/profile.yaml \
  --env examples/environments/small-public-unit-proxmox.example.yaml \
  --intent check_backup_status \
  --target all_critical_vms \
  --mode dry_run

rexecop start --operation <id>
rexecop validate --operation <id>
```

- [ ] Final state `completed`
- [ ] `.rexecop/sclite/<id>/` contains bundle artifacts
- [ ] No secrets in evidence JSON

### 5. Tecrax product profile (optional)

```bash
rexecop plan --profile tecrax --env <env> \
  --intent check_backup_status --target all_critical_vms --mode dry_run
rexecop start --operation <id>
```

### 6. Staging HTTP (CI pattern)

```bash
pytest tests/test_staging_connectors_e2e.py -q
```

Uses local HTTP stub — same shape as production `http_api` config.

### 7. Worker smoke (Phase 12)

```bash
pytest tests/test_worker_runtime.py -q
# or manual:
rexecop worker run --once
```

- [ ] Queue drain works without a long-running daemon
- [ ] Scheduling remains **host-owned** (systemd/cron) — see `docs/operator-scheduler-pattern.md`

### 8. Alpha sign-off

- [ ] Read [docs/known-limitations.md](docs/known-limitations.md)
- [ ] Apply only on non-critical targets with explicit approve
- [ ] GovEngine adapter posture verified (section below)
- [ ] Evidence vs SCLite roles understood (section below)

## Full E2E lab: profile YAML → GovEngine → SCLite bundle

This walkthrough uses the neutral `http-health-fixture` profile so domain plugins are optional.
It exercises planning, GovEngine admission on the plan path, workflow execution, validation, and
SCLite bundle emission.

### Step 1 — Prepare environment

Copy the staging template outside git and point connectors at a reachable `/health` endpoint,
or run the pytest E2E which starts an embedded HTTP stub:

```bash
pytest tests/test_http_health_check_e2e.py -q -k test_
```

For a manual run, create `~/lab/http-health.env.yaml` with `backend: http_api` and a `health`
connector action (see `examples/environments/` patterns).

### Step 2 — Plan (GovEngine gate)

```bash
export REXECOP_ROOT=~/lab/rexecop-runtime
mkdir -p "$REXECOP_ROOT"

rexecop --root "$REXECOP_ROOT" plan \
  --profile examples/profiles/http-health-fixture/profile.yaml \
  --env ~/lab/http-health.env.yaml \
  --intent http_health_check \
  --target local \
  --mode dry_run
```

Record `<operation-id>` from output.

Verify GovEngine was consulted on the mutating path when using `apply`; for `dry_run` the plan
still records governance context where applicable:

```bash
rg 'govengine_decision' "$REXECOP_ROOT/evidence/<operation-id>/" || true
```

### Step 3 — Start workflow

```bash
rexecop --root "$REXECOP_ROOT" start --operation <operation-id>
rexecop --root "$REXECOP_ROOT" status --operation <operation-id>
```

Expect terminal state `completed` for the golden path.

### Step 4 — Validate profile rules

```bash
rexecop --root "$REXECOP_ROOT" validate --operation <operation-id>
```

Expect `passed: true` and rule `http_health_check.probe_ok`.

### Step 5 — Inspect SCLite bundle (truth authority)

```bash
ls -la "$REXECOP_ROOT/sclite/<operation-id>/"
```

Expect contract artifacts, scoped ticket, receipt, and evidence sidecars. Receipt
`executed_command_count` should reflect connector steps on staging/http paths (Phase 13.2).

Compare with non-authoritative export:

```bash
test -f "$REXECOP_ROOT/receipts/<operation-id>.json" && \
  echo "receipt export is summary only — sclite/ is authoritative"
```

### Step 6 — History and redaction

```bash
rexecop --root "$REXECOP_ROOT" history --operation <operation-id>
rg -i 'api_key|token|password' "$REXECOP_ROOT/evidence/<operation-id>/" || echo "no secret leaks"
```

## GovEngine adapter posture (production vs tests)

| Adapter | Production? | Where used |
| --- | --- | --- |
| `GovEngineClient` | **Yes** — default via `default_govengine_adapter()` | Operator hosts, real governance |
| `StaticGovEngineAdapter` | **No** — bootstrap/tests only | `tests/test_*`, local fixtures |

Rules:

- Do **not** configure `StaticGovEngineAdapter` on operator hosts.
- Pytest and vertical-slice tests may inject the static adapter to avoid external GovEngine
  services — that is not a production governance boundary.
- Mutating `apply` requires a positive GovEngine admission decision **and** satisfied approval
  state; see [docs/govengine-integration.md](docs/govengine-integration.md).

Verify default adapter in code/docs:

```bash
rg 'StaticGovEngineAdapter' tests/ src/rexecop/adapters/govengine_port/
```

Production CLI paths use `default_govengine_adapter()` unless tests inject a substitute.

## Evidence vs SCLite truth

| Location | Role | Authority |
| --- | --- | --- |
| `.rexecop/evidence/<op>/` | Append-only redacted runtime events (`EvidenceManager`) | Operator telemetry / debugging |
| `.rexecop/sclite/<op>/` | Full GovEngine-integration bundle (`SCLiteArtifactEmitter`) | **Auditable truth** (SCLite) |
| `.rexecop/receipts/<op>.json` | Export summary pointing at sclite descriptors | **Not** parallel truth |
| `.rexecop/operations/`, `plans/` | Runtime operation state (file or sqlite backend) | RExecOp operator store |
| `.rexecop/queue/`, `locks/` | Concurrency and run-now backlog | Ephemeral operator mechanics |

Evidence events include `govengine_decision_requested`, `step_completed`, `receipt_generated`.
SCLite owns review semantics (`verify_ticket_use`, review bundles). When both exist, treat
`sclite/` as authoritative for audit — see [docs/evidence-model.md](docs/evidence-model.md)
and [docs/sclite-integration.md](docs/sclite-integration.md).

## Package build smoke (Phase 15)

```bash
python -m pip install build twine
rm -rf dist build *.egg-info
python -m build && python -m twine check dist/*
```

CI runs the same checks in the `package-dry-run` job. Details: [docs/distribution.md](docs/distribution.md).

## Related

- [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/profile-contract.md](docs/profile-contract.md)
- [docs/distribution.md](docs/distribution.md)
