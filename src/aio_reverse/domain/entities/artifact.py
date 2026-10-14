"""Target artifact entity (APK, Web bundle, Native .so)."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ArtifactKind(str, Enum):
    APK = "apk"
    DEX = "dex"
    SO_NATIVE = "so_native"
    WEB_BUNDLE = "web_bundle"
    WASM = "wasm"
    PCAP = "pcap"


@dataclass(frozen=True)
class Artifact:
    """Represents a target file under reverse engineering."""

    path: Path
    kind: ArtifactKind
    sha256: str
    size_bytes: int
    package_name: str | None = None
