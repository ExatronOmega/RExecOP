# Environment contract

Environment YAML binds a profile to operator infrastructure: **targets**, **connectors**,
and **safety** policy. RExecOp validates operation targets at `plan` time.

## Target semantics

Targets live under `environment.targets` as a map of names to specifications.

| Kind | YAML shape | Meaning |
| --- | --- | --- |
| **group** | `type: group` + `members: [...]` | Logical target (for example `all_critical_vms`) expanding to member host ids |
| **host** | `type: host` or omitted `type` | Single declared host id |
| **member** | not a top-level key | A host id listed under a group's `members` — valid as `--target` but resolves to that single member |

### `all_critical_vms`

`all_critical_vms` is **not** a built-in magic string. It is a conventional **group name**
that profiles and runbooks use when the environment declares:

```yaml
targets:
  all_critical_vms:
    type: group
    members:
      - vm-zabbix-01
      - vm-pbs-01
```

Operations pass `--target all_critical_vms` to address the whole group. Connector and
internal actions receive the logical target string; domain handlers may expand members
via `environment.resolve_targets`.

### Plan-time validation

`rexecop plan` rejects targets that are:

- empty;
- not a key in `environment.targets`;
- not a member of any declared `type: group`.

Helper: `rexecop.environment.targets.describe_target()` returns `kind`, `members`, and
optional `group` for member targets.

## Connectors

Each workflow `connector` step must reference a connector name present and **enabled**
in `environment.connectors`. Disabled or missing connectors fail at `plan` with
`RExecOpValidationError`.

## Safety block

`safety` carries runtime policy copied into `operation.metadata.runtime_policy`
(`max_concurrent_operations`, `target_lock_enabled`, `maintenance_windows`, …).

## Related

- [profile-contract.md](profile-contract.md)
- [connector-contract.md](connector-contract.md)
- [architecture.md](architecture.md)
