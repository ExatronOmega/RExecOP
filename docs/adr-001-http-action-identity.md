# ADR-001: HTTP action identity

## Decision

RExecOp owns canonicalization, validation and digest binding for generic `http_api` action
shapes. Profiles own expected action semantics in connector `action_shapes`. Operator
environments may override base URL, secret references, TLS CA references, timeout and retry,
but not method, path, query, body template, response projection, mutation flag or response
bound.

The canonical shape is bounded JSON containing those immutable fields. RExecOp validates it
at plan and again immediately before backend IO, stores its SHA-256 digest in operation
metadata and emits it in connector results. Execution receipts keep bounded output-record
digests for the connector step; they do not add a separate HTTP action-contract field.

GovEngine continues to govern the bounded connector/action descriptor and the already-bound
profile/environment digests. It does not interpret HTTP. No GovEngine schema change is
required for this slice. SCLite stores resulting references and digests through existing
receipt/evidence contracts; it does not interpret request semantics.

## Threat model

Without this binding, an allowed action name could be redirected from a read endpoint to a
mutating method/path, given a different body, or widened through query/projection changes.
Missing, unknown or changed shapes fail closed before network IO.

## Compatibility

Profiles without `action_shapes` retain capability-name validation. Adding `action_shapes`
is opt-in and fail-closed for every action on that connector. Tecrax Zabbix and Portainer are
the first consumers. A future mandatory core-wide requirement needs evidence from another
profile and a separate compatibility decision.

## Verified Tecrax vectors

The active Tecrax Zabbix and Portainer reachability workflows verify this contract without
moving product semantics into RExecOp:

- the planned operation carries `metadata.http_action_bindings`;
- the successful `http_api` connector result carries the same `action_contract_digest`;
- the execution receipt carries the bounded output-record digest for the HTTP connector step;
- method/path drift in the operator environment is rejected before `urlopen` backend I/O.
