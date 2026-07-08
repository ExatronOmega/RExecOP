# Release security review records

Release candidates require an explicit security/process review record before PyPI
upload. The gate is enforced by `scripts/validate_external_review_gate.py`.

## Record format

Create `docs/release-security-review/<version>.json`:

```json
{
  "schema": "rexecop.release_security_review.v0.1",
  "version": "0.2.24a0",
  "review_mode": "independent_review",
  "reviewed_at": "2026-07-08",
  "reviewer_ref": "reviewer:example",
  "surfaces": [
    "governance_admission_binding",
    "mutation_gates",
    "connector_output_safety",
    "release_train_scripts",
    "supply_chain_workflow"
  ],
  "notes": "Independent review completed for release candidate."
}
```

`review_mode` must be one of:

- `independent_review` — completed by a reviewer other than the sole implementer
- `solo_reviewed_alpha_risk` — explicit solo-maintainer alpha risk acceptance (`notes` required)

## Gate

```bash
python scripts/validate_external_review_gate.py --version <version>
```

Wired into `publish.yml` before upload and alpha sign-off checks.
