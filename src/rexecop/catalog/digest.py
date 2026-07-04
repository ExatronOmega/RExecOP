from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from rexecop.errors import RExecOpValidationError


def canonical_digest(value: Any) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def yaml_document_digest(path: Path) -> str:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RExecOpValidationError(f"cannot digest yaml document: {path}") from exc
    return canonical_digest(value)


def text_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def profile_snapshot_digest(root: Path) -> str:
    snapshot: list[dict[str, str]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if "__pycache__" in path.parts or path.suffix not in {".yaml", ".yml", ".json"}:
            continue
        snapshot.append(
            {
                "path": path.relative_to(root).as_posix(),
                "digest": yaml_document_digest(path),
            }
        )
    if not snapshot:
        raise RExecOpValidationError(f"profile snapshot is empty: {root}")
    return canonical_digest(snapshot)
