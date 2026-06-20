from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class BoundedText:
    text: str
    digest: str
    truncated: bool
    original_bytes: int


def bounded_text(value: str, *, max_bytes: int) -> BoundedText:
    if max_bytes < 1:
        max_bytes = 1
    raw = value.encode("utf-8", errors="replace")
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    truncated = len(raw) > max_bytes
    if not truncated:
        return BoundedText(
            text=value.strip(),
            digest=digest,
            truncated=False,
            original_bytes=len(raw),
        )
    clipped = raw[:max_bytes].decode("utf-8", errors="ignore")
    return BoundedText(
        text=clipped.strip(),
        digest=digest,
        truncated=True,
        original_bytes=len(raw),
    )
