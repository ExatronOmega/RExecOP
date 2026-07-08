# Release evidence

Store post-publish public-index smoke output for a released line.

Preferred path:

```bash
python scripts/validate_public_index_release_smoke.py \
  --version <version> \
  --write-evidence \
  --verify-post-publish
```

This records `clean_install_smoke_ok:rexecop==<version>` and runs offline
`validate_release_train_preflight.py --post-publish`.

Manual fallback: run `validate_clean_install_smoke.py`, copy the stdout marker into
`docs/release-evidence/<version>.md`, then run preflight `--post-publish`.

This directory stays empty until a release is published and verified on PyPI.
