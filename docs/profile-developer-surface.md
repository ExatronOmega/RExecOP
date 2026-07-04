# Profile developer surface

RExecOp exposes a neutral discoverability layer for profiles, connector backends,
internal actions and runtime capabilities. These commands are **metadata and
compatibility tooling** — they do not execute connectors, resolve secret values,
or replace GovEngine admission.

## Developer journey

Typical profile-author flow before operator runs:

```text
profile lint --track readonly
  -> profiles show (intents, tracks, developer_check)
  -> secrets doctor --env <environment.yaml>
  -> operations unavailable --catalog <targets.yaml> --target <id>   # when using a catalog
  -> plan / operation review
```

`run_profile_developer_check()` (surfaced in `profiles show`) runs conformance,
plugin compatibility and GovEngine G3 `govengine_governance` compatibility
**without** a runtime store.

## Profile discoverability

```bash
rexecop profiles list
rexecop profiles show tecrax
rexecop profiles show examples/profiles/runtime-fixture/profile.yaml --track readonly
```

`profiles list` summarizes registered `rexecop.profiles` entry points with
readonly/mutation compatibility status.

`profiles show` returns:

- profile summary: version, intents, required capabilities, per-track conformance;
- `developer_check`: conformance + `plugin_compatibility` + `govengine_governance`;
- bounded `extension_manifest` slice (`required_contracts`, `supported_tracks`).

JSON schema: `rexecop.profile_show.v0.1`.

## Conformance categories

`profile lint` and conformance results include categorized checks:

| Category | Meaning |
| --- | --- |
| `readonly` | Read-only mode and side-effect class checks |
| `mutation` | Mutation-candidate contract checks |
| `reaction` | Reaction observation declaration and reaction pack |
| `catalog` | Operation catalog projection and intent metadata |
| `connector` | Workflow connector contracts |
| `validation` | Validation rule file presence and profile-local paths |

Tracks remain `readonly`, `mutation` or `all`. Categories are orthogonal to tracks.

## Extension manifest

```bash
rexecop profile manifest
```

Emits `rexecop.extension_manifest.v0.1` with:

- `compatibility_version` (current rexecop version);
- `required_contracts` (`profile_contract`, `connector_contract`, SCLite schema refs);
- `supported_tracks` (`readonly`, `mutation`, `all`);
- registered `profiles`, `connector_backends`, `internal_actions`, `secret_resolvers`;
- canonical `digest` of the manifest payload.

Use this when authoring or certifying profile/plugin packages against the
current rexecop host line.

## Connector discoverability

```bash
rexecop connectors list
rexecop connectors show http_api
```

Built-in backends include `mock`, `http_api`, `local_shell_readonly`,
`ssh_readonly`, and `static_fixture`. Plugin backends registered through
`rexecop.connector_backends` appear with `certification_tier: plugin`.

Each descriptor reports `supported_modes`, neutral `capability_descriptors`, and
`compatibility_version`. See [connector-contract.md](connector-contract.md).

## Capabilities

```bash
rexecop capabilities list
```

Lists neutral runtime capabilities and their source (`rexecop.core`,
`rexecop.connector_backends`, `rexecop.internal_actions`, secret resolver
primitives). Profile-declared capability names in intent catalog metadata are
separate from this runtime registry.

## Plugin compatibility report

`build_plugin_compatibility_report()` (used by `profiles show` and developer
checks) verifies that registered `rexecop.connector_backends` factories return a
valid runtime and that `rexecop.internal_actions` entry points load. Failures are
bounded JSON errors without backend IO.

## Authority boundaries

| Surface | Owns | Does not own |
| --- | --- | --- |
| `profiles *` | Profile metadata, conformance, plugin registration | Domain semantics, policy verdicts |
| `connectors *` | Backend descriptors and certification tier | Connector execution |
| `capabilities list` | Neutral capability registry | Target catalog capabilities |
| `profile manifest` | Host extension contract | Profile content |
| `operations unavailable` | Technical applicability reasoning | GovEngine admission |