"""Use case: Emulate and verify a reversed cryptographic or signing routine."""

from typing import Any
from aio_reverse.application.ports.execution_sandbox_port import IExecutionSandboxPort
from aio_reverse.domain.entities.crypto import CryptoRoutine
from aio_reverse.domain.entities.evidence import EvidenceRecord, ProvenanceKind


class EmulateCryptoExecutionUseCase:
    """Runs extracted crypto logic in an isolated sandbox and validates output."""

    def __init__(self, sandbox: IExecutionSandboxPort):
        self._sandbox = sandbox

    def execute(
        self,
        routine: CryptoRoutine,
        test_inputs: list[Any],
        environment_shim: dict[str, Any] | None = None,
    ) -> EvidenceRecord:
        """Executes the routine inside the sandbox and returns an Evidence record."""
        if not routine.code_snippet:
            raise ValueError(f"Routine {routine.name} has no code snippet to execute.")

        result = self._sandbox.execute_snippet(
            code_or_binary=routine.code_snippet,
            entrypoint=routine.name,
            arguments=test_inputs,
            environment_shim=environment_shim,
        )

        return EvidenceRecord(
            evidence_id=f"ev_emu_{routine.name}",
            tool_name="execution_sandbox",
            provenance=ProvenanceKind.DERIVATION,
            data={"result": result, "routine": routine.name},
        )
