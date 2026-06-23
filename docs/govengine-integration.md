# GovEngine integration

RExecOp consumes GovEngine for **governance decisions only**. GovEngine defines and validates
admission envelopes and runner request/receipt contracts; it does **not** execute operations.

```text
Profile workflow
  -> RExecOp OperationPlan
  -> GovEngineRequest (from plan preview + operation context)
  -> GovEngineAdapter.evaluate()
  -> GovEngineDecision
  -> RExecOp state transition + evidence
  -> controlled execution when allowed (and approved if required)
```

## Adapters

| Adapter | Use |
| --- | --- |
| `GovEngineClient` | **Default** production path via `compose_runtime_admission_result()` |
| `StaticGovEngineAdapter` | Bootstrap and tests only — **not** production governance |

Factory: `default_govengine_adapter()` in `adapters/govengine_port/adapter.py`.

The static adapter is explicitly marked `bootstrap_only` and documented as non-production in
`static_adapter.py` and [safety-model.md](safety-model.md).

## Dependency

```text
govengine>=0.15.0,<0.16
```

Pinned compatible with the SCLite alpha line used by RExecOp (`sclite-core>=1.0.4,<1.1`).

## PolicyEngine integration

When the environment declares `policy_pack`, RExecOp:

1. Compiles the pack at `plan` and stores it on the operation.
2. Evaluates operation policy and fails plan unless the verdict is a plain `allow`
   with no obligations or constraints.
3. Projects the operation verdict to `govengine_request_preview.policy_decision`
   (via `policy_verdict_to_gov_policy_decision()`).
4. Re-evaluates per connector at invoke time in `CompositeConnectorRuntime` before backends run.

Without `policy_pack`, `GovEngineClient` behavior is unchanged (compose inputs from preview overrides or fail-closed defaults).

RExecOp does not satisfy GovEngine PolicyEngine obligations by implication. If
GovEngine returns `allow_with_obligations`, `approval_required`, `deny`, blockers,
obligations, or constraints on the policy-pack path, RExecOp treats that as
not executable until a future enforcement adapter explicitly implements those controls.

## Decision mapping

`RuntimeAdmissionResult` from GovEngine maps to RExecOp `GovEngineDecisionType`:

| GovEngine outcome | RExecOp effect (mutating modes) |
| --- | --- |
| `allowed` | May proceed to execution after approval state satisfied |
| `approval_required` | `waiting_for_approval` — no mutating connector calls |
| `blocked`, `read_only_only`, `human_required`, … | `blocked` or wait — no mutation |
| `error` / invalid admission | Fail closed |

Evidence events: `govengine_decision_requested`, `govengine_decision_received`.

## Apply hard rule

Mutating modes (`apply`, `recovery`) require:

1. Positive GovEngine `allowed` decision recorded on the operation
2. Operation in `approved` state (manual `rexecop approve` when `approval_required`)
3. Connector-level check: `http_api` mutating actions also verify `mutating_allowed` at runtime

Read-only modes (`dry_run`, `observe`, `emergency_readonly`) auto-approve at start and refuse
mutating connector actions at the connector runtime layer.

## Runner contracts

`build_runner_request_preview()` materializes GovEngine runner request shapes from the
operation plan. Post-execution receipt binding uses GovEngine validation helpers where applicable.

## SCLite bridge

Admission metadata from `operation.metadata["govengine_admission"]` is bridged into SCLite
`policy_decision` and scoped ticket approval fields during bundle emission
(`adapters/sclite_port/govengine_policy_bridge.py`).

## Boundary

GovEngine validates/contracts admission and runner records. RExecOp remains the runner,
orchestrator, and executor that invokes profile-declared workflow steps and connectors.
