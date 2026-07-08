# Release evidence

Store post-publish public-index smoke output for a released line.

After `python scripts/validate_clean_install_smoke.py` succeeds for version `<version>`,
record the stdout marker here as `docs/release-evidence/<version>.md` or in the matching
`CHANGELOG` section. Then run:

```bash
python scripts/validate_release_train_preflight.py --post-publish
```

This directory is intentionally empty until a release is published and verified on PyPI.
