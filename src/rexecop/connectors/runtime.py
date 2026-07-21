from __future__ import annotations

from rexecop.connectors.base import ConnectorRequest, ConnectorResponse, ConnectorRuntime
from rexecop.connectors.mock_runtime import MockConnectorRuntime
from rexecop.runtime.mutation_posture import require_mutation_execution_enabled


def default_connector_runtime() -> ConnectorRuntime:
    return MockConnectorRuntime()


class ConnectorDispatcher:
    def __init__(self, runtime: ConnectorRuntime | None = None) -> None:
        self.runtime = runtime or default_connector_runtime()

    def invoke(self, request: ConnectorRequest) -> ConnectorResponse:
        require_mutation_execution_enabled(request.mode)
        return self.runtime.invoke(request)
