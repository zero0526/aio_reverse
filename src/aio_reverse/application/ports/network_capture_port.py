"""Abstract Port for network traffic capture (Mitmproxy / Tshark)."""

from abc import ABC, abstractmethod
from pathlib import Path
from aio_reverse.domain.entities.endpoint import ApiEndpoint


class INetworkCapturePort(ABC):
    """Port for capturing, decrypting, and analyzing network traffic."""

    @abstractmethod
    def start_capture_session(self, port: int) -> str:
        """Start proxy listener or capture interface."""
        ...

    @abstractmethod
    def stop_capture_session(self, session_id: str) -> Path:
        """Stop capture and flush recorded flows to storage."""
        ...

    @abstractmethod
    def extract_observed_endpoints(self, dump_path: Path) -> list[ApiEndpoint]:
        """Parse capture dump and return observed API endpoints with redaction."""
        ...
