"""Use case: Trace cryptographic, signature, and token generation routines."""

from aio_reverse.application.ports.decompiler_port import IDecompilerPort
from aio_reverse.application.ports.dynamic_hook_port import IDynamicHookPort
from aio_reverse.domain.entities.artifact import Artifact
from aio_reverse.domain.entities.crypto import CryptoRoutine


class TraceCryptoRoutineUseCase:
    """Traces and extracts encryption, hashing, and signature logic."""

    def __init__(
        self,
        decompiler: IDecompilerPort,
        dynamic_hook: IDynamicHookPort | None = None,
    ):
        self._decompiler = decompiler
        self._dynamic_hook = dynamic_hook

    def execute(self, artifact: Artifact) -> list[CryptoRoutine]:
        """Scans artifact for cryptographic logic and returns routines."""
        routines = self._decompiler.find_crypto_routines(artifact)
        return routines
