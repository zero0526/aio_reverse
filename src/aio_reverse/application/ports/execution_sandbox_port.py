"""Abstract Port for executing reversed code in an emulated environment."""

from abc import ABC, abstractmethod
from typing import Any


class IExecutionSandboxPort(ABC):
    """Port for running isolated execution environments (V8 / Unidbg / CDP)."""

    @abstractmethod
    def execute_snippet(
        self,
        code_or_binary: str | bytes,
        entrypoint: str,
        arguments: list[Any],
        environment_shim: dict[str, Any] | None = None,
        timeout_ms: int = 1000,
        memory_limit_mb: int = 64,
    ) -> Any:
        """Execute a reversed function in an isolated sandbox with resource bounds."""
        ...
