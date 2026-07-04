from __future__ import annotations

from typing import Any

from rexecop.observability.structured_log import (
    StructuredLogRefs,
    build_structured_log_event,
)
from rexecop.storage.port import RuntimeStore


class StructuredLogEmitter:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def emit(
        self,
        *,
        event_kind: str,
        correlation_id: str,
        message: str,
        refs: StructuredLogRefs | None = None,
        failure_class: str = "",
        details: dict[str, Any] | None = None,
    ) -> str:
        event = build_structured_log_event(
            event_kind=event_kind,
            correlation_id=correlation_id,
            message=message,
            refs=refs,
            failure_class=failure_class,
            details=details,
        )
        self.store.save_structured_log_event(event)
        return str(event["event_id"])