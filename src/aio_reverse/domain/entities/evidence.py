"""Evidence Record entity for tracing and reproducibility."""

from dataclasses import dataclass
from enum import Enum
from typing import Any
import time


class ProvenanceKind(str, Enum):
    OBSERVATION = "observation"  # Read directly from bytes/memory/traffic
    DERIVATION = "derivation"    # Logically computed from observations
    INFERENCE = "inference"      # Heuristic / hypothesis
    UNKNOWN = "unknown"          # Missing or unverified data


@dataclass(frozen=True)
class EvidenceRecord:
    """Container for verifiable findings with complete provenance."""

    evidence_id: str
    tool_name: str
    provenance: ProvenanceKind
    data: dict[str, Any]
    confidence_score: float = 1.0
    timestamp_unix: float = time.time()
