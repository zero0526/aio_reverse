"""Abstract Port for decompilation engines (JADX, etc.)."""

from abc import ABC, abstractmethod
from aio_reverse.domain.entities.artifact import Artifact
from aio_reverse.domain.entities.endpoint import ApiEndpoint
from aio_reverse.domain.entities.crypto import CryptoRoutine


class IDecompilerPort(ABC):
    """Port for static code decompilation and analysis."""

    @abstractmethod
    def decompile_artifact(self, artifact: Artifact) -> bool:
        """Decompile the target artifact into a temporary workspace."""
        ...

    @abstractmethod
    def extract_api_endpoints(self, artifact: Artifact) -> list[ApiEndpoint]:
        """Extract declared or referenced HTTP/WebSocket endpoints."""
        ...

    @abstractmethod
    def find_crypto_routines(self, artifact: Artifact) -> list[CryptoRoutine]:
        """Scan decompiled code for signing, hashing, and encryption calls."""
        ...
