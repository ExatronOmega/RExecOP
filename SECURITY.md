# Security policy

RExecOP is a governed execution runtime. Please report suspected vulnerabilities
privately through GitHub Security Advisories for this repository. Do not include
production credentials, customer data, host inventories, or private topology in
issues, logs, or public reproductions.

Supported security fixes target the current prerelease line until the 1.0 support
policy is published. A vulnerability exception is release-blocking unless it has
an explicit owner, affected scope, expiry date, and compensating controls recorded
in release evidence.

Security-sensitive changes must run the `security_regression` pytest marker and
the normal repository gates. See `docs/security-threat-model.md` for the bounded
trust model and fail-closed invariants.
