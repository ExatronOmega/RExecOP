# Bounded security threat model

## Trust boundaries

- GovEngine decides policy admission; RExecOP validates and enforces the bound
  execution request immediately before connector I/O.
- SCLite 2.0 remains the frozen truth/evidence kernel. RExecOP projects into its
  existing contracts and does not define new SCLite schemas.
- Connector configuration, secret references, SSH identity files, known-hosts
  files, and operator egress controls are operator-owned inputs.
- Connector responses, pagination links, redirects, remote output, diagnostics,
  plugin output, and profile-supplied public-field declarations are untrusted.

## Required invariants

HTTP credentials are scoped to the normalized `(scheme, host, effective_port)`
origin. Response-derived pagination targets are validated before request creation,
automatic redirects are rejected, pagination loops are bounded, and auth cannot
replace transport-reserved headers.

Stable SSH uses strict host-key verification. `accept-new` is restricted to an
explicit lab or fixture posture; disabled verification is not a stable posture.
Operator files must exist before I/O, be regular non-symlinks, have the expected
owner, and reject group/world write (plus all group/world access for identities).
Host, user, and port values are validated before argv construction.

Shareable evidence is allowlist-first. Structured state, response bodies, and
diagnostics are digest-only by default. Only exact paths may be disclosed;
wildcard subtrees never widen a public projection.

## Residual deployment dependency

Hostname validation alone cannot prevent DNS rebinding. Stable live deployments
therefore require operator-enforced egress/DNS controls until RExecOP binds a
resolved address set to the transport connection. The 1.0 doctor gate must expose
and fail closed on that dependency; this prerelease does not claim transport-level
DNS pinning.

## Regression scope

`pytest -m security_regression` covers malicious pagination, origin/port changes,
reserved-header injection, SSH posture/path/argv failures, and negative public
projection behavior. Release qualification also requires the full test suite and
cross-repository contract gates.
