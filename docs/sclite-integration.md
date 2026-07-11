# SCLite integration

RExecOp does **not** own long-term auditable truth. SCLite does. RExecOp maps completed
operation lifecycles into SCLite-compatible artifact bundles without forking a parallel schema.

RExecOp does own orchestration semantics and the corresponding reaction,
trigger, watchdog and automation contract resources. The explicit
`ORCHESTRATION_SCHEMA_RESOLVER` binds these resources under the `rexecop.io`
namespace. SCLite remains the neutral byte/schema verifier and does not become
the runtime or policy owner.

With SCLite 2.0 these builders and semantic verifiers are implemented directly
under `rexecop.contracts`; no deprecated SCLite owner modules are imported.
Historical v0.1 artifacts retain their original embedded `schema_ref` and are
resolved explicitly by the RExecOp owner resolver.

Release candidates are checked by
`scripts/validate_f4_conformance_matrix.py`, which requires a fixed local
wheelhouse and reports exact candidate artifact digests rather than testing
against an arbitrary branch tip.

## Authority model

Paths use `<root>/` for the selected runtime root (`--root`, `REXECOP_ROOT`, named
`--instance`, or fallback `./.rexecop`).

| Layer | Location | Role |
| --- | --- | --- |
| **SCLite artifacts** | `<root>/sclite/<operation_id>/` | Authoritative contracts, tickets, receipts, evidence |
| **RExecOp internal events** | `<root>/evidence/<operation_id>/` | Runtime telemetry (redacted) |
| **RExecOp receipt export** | `<root>/receipts/<operation_id>.json` | Summary pointer (`authority: sclite_artifact` or export marker) |

`Operation.sclite_refs` stores descriptor links per artifact role after emission.

## Current emission path

Primary emitter: `SCLiteArtifactEmitter` (`adapters/sclite_port/emitter.py`)

Full bundle helpers: `adapters/sclite_port/full_bundle.py`

Bundle profile aligned with `sclite/examples/govengine-integration/`:

- Six lifecycle artifacts (`contract-lifecycle-v0.2` roles)
- `execution_ticket.v0.3` scoped ticket with `ticket_use` binding
- Receipt-bounded `evidence_contract` (no live-vuln claims)
- `trust_profile_ref.json` and `carrier_profile_ref.json` sidecars
- Optional `kernel_guard_manifest.json` when `REXECOP_KERNEL_GUARD_KEY` is set
  to a production key of at least 32 UTF-8 bytes; shorter values fail closed in
  SCLite. Otherwise the sidecar is `not_required`. RExecOp owns secret custody;
  SCLite enforces only type/length and does not claim entropy validation.
- Fixture/lab guard via `adapters/sclite_port/fixture_bundle.py` (`emit_fixture_operation_bundle`) — not used in production emit
- `verify_ticket_use` + `review_bundle` → verdict `pass` on emission
- Explicit `target_host` resolution for scope-fidelity (`adapters/sclite_port/target_host.py`)
- GovEngine admission metadata bridged into `policy_decision` (`govengine_policy_bridge.py`)

## Deprecated path

`PlaceholderSCLiteEmitter` — offline/bootstrap tests only via `rexecop.examples.bootstrap_receipt`
(deprecated). `OperationController.export_placeholder_receipt()` warns and delegates there.
Do not treat placeholder JSON as long-term truth.

## Artifact slots

| Role | Schema |
| --- | --- |
| `intent_contract` | `schemas/intent_contract.v0.2.schema.json` |
| `policy_decision` | `schemas/policy_decision.v0.3.schema.json` |
| `execution_contract` | `schemas/execution_contract.v0.3.schema.json` |
| `execution_ticket` | `schemas/execution_ticket.v0.3.schema.json` |
| `execution_receipt` | `schemas/execution_receipt.v0.2.schema.json` |
| `evidence_contract` | `schemas/evidence_contract.v0.2.schema.json` |
| `trust_profile_ref` | `schemas/trust_profile_ref.v0.1.schema.json` |
| `carrier_profile_ref` | `schemas/carrier_profile_ref.v0.1.schema.json` |
| `kernel_guard_manifest` | optional — `schemas/kernel_guard_hmac_v1.schema.json` or `not_required` |

## Event → artifact mapping

Internal evidence events declare future SCLite mapping via `EVENT_SCLITE_MAPPING` in
`adapters/sclite_port/contracts.py`. Real emission occurs at lifecycle boundaries (plan,
governance, completion), not per debug-level internal event.

## GovEngine linkage

`policy_decision` and ticket approval status derive from `operation.govengine_decision_type`
and `operation.metadata["govengine_admission"]` on mutating paths. Read-only operations use
scoped ticket defaults appropriate for dry-run review (`approved_for_dry_run`).

## Dependency

```text
sclite-core==1.0.9
```

Aligned with GovEngine pin strategy in `pyproject.toml`.

## Boundary

SCLite records auditable truth. RExecOp projects operation lifecycle outcomes into SCLite
artifact shapes. RExecOp must not treat `<root>/receipts/` exports as authoritative when
`<root>/sclite/` bundles exist for the same operation.
