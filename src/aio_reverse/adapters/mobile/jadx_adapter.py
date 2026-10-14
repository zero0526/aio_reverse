"""JADX Decompiler Adapter implementing IDecompilerPort."""

from aio_reverse.application.ports.decompiler_port import IDecompilerPort
from aio_reverse.domain.entities.artifact import Artifact
from aio_reverse.domain.entities.endpoint import ApiEndpoint
from aio_reverse.domain.entities.crypto import CryptoRoutine


class JadxAdapter(IDecompilerPort):
    """Controls headless JADX engine via CLI/bridge."""

    def __init__(self, jadx_jar_path: str = "jadx-headless"):
        self._jadx_jar_path = jadx_jar_path

    def decompile_artifact(self, artifact: Artifact) -> bool:
        # Skeleton: Invokes JADX bridge or CLI with bounded resources
        return True

    def extract_api_endpoints(self, artifact: Artifact) -> list[ApiEndpoint]:
        # Skeleton: Scans Retrofit / OkHttp / HttpURLConnection annotations
        return []

    def find_crypto_routines(self, artifact: Artifact) -> list[CryptoRoutine]:
        # Skeleton: Finds calls to javax.crypto.Cipher, MessageDigest, Mac
        return []
