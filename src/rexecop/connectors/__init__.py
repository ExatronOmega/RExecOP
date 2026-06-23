"""Connector adapters."""

from typing import TYPE_CHECKING, Any

from rexecop.connectors.base import ConnectorRequest, ConnectorResponse, ConnectorRuntime
from rexecop.connectors.mock_runtime import MockConnectorRuntime
from rexecop.connectors.runtime import ConnectorDispatcher, default_connector_runtime

if TYPE_CHECKING:
    from rexecop.connectors.composite_runtime import CompositeConnectorRuntime


def __getattr__(name: str) -> Any:
    if name in {"CompositeConnectorRuntime", "build_connector_runtime"}:
        from rexecop.connectors import composite_runtime

        return getattr(composite_runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "CompositeConnectorRuntime",
    "ConnectorDispatcher",
    "ConnectorRequest",
    "ConnectorResponse",
    "ConnectorRuntime",
    "MockConnectorRuntime",
    "build_connector_runtime",
    "default_connector_runtime",
]
