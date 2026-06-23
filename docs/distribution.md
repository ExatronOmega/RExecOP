# Distribution and installation

RExecOp `0.2.6a0` is the current **unpublished alpha source line**. The latest
PyPI package is [`rexecop==0.2.5a0`](https://pypi.org/project/rexecop/0.2.5a0/),
which predates full B2 and R4c. Maturity limits in
[known-limitations.md](known-limitations.md) apply to both.

## Supported install paths

| Path | When to use |
| --- | --- |
| **PyPI** (`pip install rexecop==0.2.5a0`) | Evaluation of the published pre-B2 package only |
| Coordinated editable source (`pip install -e`) | B2/R4c development and operator lab |
| Wheel from `dist/` after `python -m build` | Offline install, internal mirrors |
| Git URL install | Pin a commit or tag without PyPI |

## Prerequisites

- Python **3.11+**
- Network access to install pinned dependencies:
  - `govengine>=0.16.0,<0.17` for the source line
  - `sclite-core>=1.0.4,<1.1`
- Optional domain profile: [`tecrax`](https://pypi.org/project/tecrax/) or Git

## Install from PyPI

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "rexecop==0.2.5a0"
rexecop version
```

With Tecrax profile (after `tecrax` is on PyPI at a compatible version):

```bash
python -m pip install "rexecop[tecrax]==0.2.5a0"
```

If the `tecrax` extra cannot resolve from PyPI yet, install Tecrax from Git:

```bash
python -m pip install "rexecop==0.2.5a0"
python -m pip install "tecrax @ git+https://github.com/rozmiarD/tecrax.git@main"
```

## Coordinated editable install

```bash
git clone https://github.com/rozmiarD/RExecOP.git
cd RExecOP
python -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
git clone https://github.com/rozmiarD/GovEngine.git ../govengine
python -m pip install -e ../govengine
python -m pip install -e ".[dev]"

git clone https://github.com/rozmiarD/tecrax.git ../tecrax
python -m pip install -e ../tecrax

rexecop version
python scripts/validate_public_truth.py
```

## Build a wheel locally

Matches the CI `package-dry-run` job:

```bash
python -m pip install --upgrade pip build twine
python -m pip install -e /path/to/govengine
python -m pip install "sclite-core>=1.0.4,<1.1"
rm -rf dist build *.egg-info
python -m build
python -m twine check dist/*
python scripts/validate_distribution.py dist
```

## Install from Git (no local clone)

```bash
python -m pip install "govengine @ git+https://github.com/rozmiarD/GovEngine.git@main"
python -m pip install "rexecop @ git+https://github.com/rozmiarD/RExecOP.git@main"
```

Do not install RExecOp `main` against the published GovEngine `0.15.0` wheel;
that wheel does not provide the enforcement-plan imports required by B2.

## Private index / GitHub Packages (operator-owned)

Operators may mirror wheels into an internal PyPI-compatible index or GitHub Packages.
See prior internal-mirror examples in git history if needed.

## Version and doc alignment

Before sharing an install artifact outside your host:

```bash
python scripts/validate_public_truth.py
pytest -q
```

See [OPERATOR_RUNBOOK.md](../OPERATOR_RUNBOOK.md) for secrets, staging environments, and
apply safety. See [OPERATOR_LAB_RUNBOOK.md](../OPERATOR_LAB_RUNBOOK.md) for the full
profile → GovEngine → SCLite lab path.

## Related

- [README.md](../README.md) — project overview
- [CHANGELOG.md](../CHANGELOG.md) — release history
- [known-limitations.md](known-limitations.md) — alpha non-claims
