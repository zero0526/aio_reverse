"""Use case: Discover and correlate network API surface from static and dynamic evidence."""

from aio_reverse.application.ports.decompiler_port import IDecompilerPort
from aio_reverse.application.ports.network_capture_port import INetworkCapturePort
from aio_reverse.domain.entities.artifact import Artifact
from aio_reverse.domain.entities.endpoint import ApiEndpoint


class DiscoverApiSurfaceUseCase:
    """Discovers API endpoints by correlating decompiled code with network captures."""

    def __init__(
        self,
        decompiler: IDecompilerPort,
        network_capture: INetworkCapturePort | None = None,
    ):
        self._decompiler = decompiler
        self._network_capture = network_capture

    def execute(self, artifact: Artifact) -> list[ApiEndpoint]:
        """Runs discovery and returns extracted API endpoints."""
        endpoints = self._decompiler.extract_api_endpoints(artifact)
        # Skeleton: can correlate with observed network capture endpoints if available
        return endpoints
