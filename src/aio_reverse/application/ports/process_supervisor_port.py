"""Abstract Port for OS process lifecycle supervision."""

from abc import ABC, abstractmethod
from pathlib import Path


class IProcessSupervisorPort(ABC):
    """Port for supervising external processes, timeouts, and cleanups."""

    @abstractmethod
    def spawn_supervised_process(
        self,
        command: list[str],
        cwd: Path | None = None,
        timeout_seconds: int = 30,
        memory_limit_bytes: int | None = None,
    ) -> int:
        """Spawn a child process in an isolated process group."""
        ...

    @abstractmethod
    def terminate_process_group(self, pgid: int) -> None:
        """Forcefully terminate an entire process group."""
        ...

    @abstractmethod
    def cleanup_workspace(self, workspace_path: Path) -> None:
        """Safely remove temporary directories and sockets."""
        ...
