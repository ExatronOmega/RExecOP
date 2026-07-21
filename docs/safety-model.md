# Safety model

RExecOp implements **Regulated Execution Operations** — controlled, auditable workflow execution,
not unconstrained automation.

## Hard rules

1. **Stable means read-only** — the default `stable_read_only` runtime posture blocks
   `apply` and `recovery` before execution and again before connector I/O.
2. **No apply without governance** — the explicit `lab_only` mechanics posture does not
   bypass GovEngine admission, approval, permit, lease or fencing checks.
3. **No ad hoc workflows** — only profile-declared steps may run; the workflow runner never
   invents steps.
4. **Evidence is mandatory** — state transitions and step boundaries emit internal evidence events.
5. **Secrets never in store** — passwords, tokens, and API keys are redacted from evidence;
   environment YAML must use `secret_ref` (inline secrets rejected at plan time).
6. **LLM is not an executor** — models may analyze escalation packages later; they do not bypass
   RExecOp or GovEngine.
7. **Profiles stay out of core** — no Tecrax/Ravenclaw domain logic in `src/rexecop` (CI grep).

## Connector posture

- `http_api` is generic — infrastructure APIs are environment config instances, not core code.
- `http_api` may invoke **only** capabilities declared in the profile connector contract.
- Mutating `http_api` calls require GovEngine `allowed` for the operation and apply mode.
- `local_shell_readonly` refuses `apply` / `recovery` modes; commands must be allowlisted.
- Connector responses pass through evidence redaction (including API-shaped payloads).

## GovEngine adapter posture

| Adapter | Production? |
| --- | --- |
| `GovEngineClient` | Yes — default adapter |
| `StaticGovEngineAdapter` | **No** — bootstrap and tests only |

The static adapter is documented as non-production in code, tests, and
[govengine-integration.md](govengine-integration.md).

## Operator defaults

- Default operation mode: `dry_run` (CLI default on `plan`)
- `apply` requires explicit mode selection, `REXECOP_MUTATION_POSTURE=lab_only`, GovEngine
  clearance, and approval when required; `lab_only` is not stable or production certification
- Escalation packages list **descriptive** safe next options — they are not auto-executed commands
- Real environment and secrets files live **outside git**; use `*.example.yaml` templates in-repo
- Target lock and queue limit concurrent mutating work per environment policy
- Maintenance windows block apply when configured

## Runtime storage

Runtime roots (`--root`, named `--instance`, or fallback `./.rexecop`) are gitignored.
Operators must verify exports and evidence do not contain resolved secrets before sharing
artifacts outside the host.

## Pre-alpha limits

RExecOp is **alpha** software. See [known-limitations.md](known-limitations.md) and
[OPERATOR_RUNBOOK.md](../OPERATOR_RUNBOOK.md) for operator procedures and explicit non-claims.

## Related documents

- [architecture.md](architecture.md) — layer boundaries
- [connector-contract.md](connector-contract.md) — `http_api` and secrets
- [govengine-integration.md](govengine-integration.md) — apply gating
- [sclite-integration.md](sclite-integration.md) — truth authority
