"""Abstract Persistence Port for storing targets, endpoints, and evidence."""

from abc import ABC, abstractmethod
from aio_reverse.domain.entities.artifact import Artifact
from aio_reverse.domain.entities.endpoint import ApiEndpoint
from aio_reverse.domain.entities.evidence import EvidenceRecord


class IPersistencePort(ABC):
    """Port for persisting analysis targets, extracted endpoints, and evidence."""

    @abstractmethod
    def save_artifact(self, artifact: Artifact) -> None:
        """Store target artifact metadata."""
        ...

    @abstractmethod
    def get_artifact(self, sha256: str) -> Artifact | None:
        """Retrieve artifact by SHA-256."""
        ...

    @abstractmethod
    def save_endpoints(self, artifact_sha256: str, endpoints: list[ApiEndpoint]) -> None:
        """Store discovered API endpoints bound to an artifact."""
        ...

    @abstractmethod
    def get_endpoints(self, artifact_sha256: str) -> list[ApiEndpoint]:
        """Retrieve all discovered endpoints for an artifact."""
        ...

    @abstractmethod
    def save_evidence(self, target_sha256: str, evidence: EvidenceRecord) -> None:
        """Record an evidence entry with complete provenance."""
        ...

    @abstractmethod
    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        """Retrieve evidence by its unique ID."""
        ...
