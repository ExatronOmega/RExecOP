# Release evidence

Release evidence is a versioned `rexecop.release_evidence.v1` JSON record. It binds
the published version to the exact source commit, workflow run, wheel/sdist SHA-256
digests, installed GovEngine/SCLite/RExecOp/Tecrax versions and doctor result. The
record carries its own canonical `record_digest`.

Preferred path:

```bash
python scripts/validate_public_index_release_smoke.py \
  --version <version> \
  --dist-dir dist \
  --evidence-output .release-train/rexecop-release-evidence-<version>.json \
  --write-evidence \
  --verify-post-publish
```

`publish.yml` uploads the record as a GitHub Actions artifact, attests it and
persists it on the dedicated `release-evidence` Git branch. Before another
upload, release-mode preflight downloads and validates the preceding supported
line's record from that durable ref:

```bash
python scripts/validate_release_train_preflight.py \
  --release \
  --previous-evidence .release-train/rexecop-release-evidence-<previous>.json
```

Missing evidence, a mismatched version, altered record digest, absent wheel/sdist,
non-green doctor status or incomplete installed-version inventory fails closed.
`.github/workflows/repair-release-evidence.yml` is the bounded manual recovery path
for an already-published line; it reruns the public-index smoke, downloads the exact
public wheel and sdist, and publishes a replacement evidence record. A replacement
may explicitly name the prior line in `supersedes`.
