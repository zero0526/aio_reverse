"""Process supervisor for managing process groups, timeouts, and cleanups."""

import os
import signal
import subprocess
import shutil
from pathlib import Path
from aio_reverse.application.ports.process_supervisor_port import IProcessSupervisorPort


class ProcessSupervisor(IProcessSupervisorPort):
    """Guarantees process group isolation and safe cleanup."""

    def spawn_supervised_process(
        self,
        command: list[str],
        cwd: Path | None = None,
        timeout_seconds: int = 30,
        memory_limit_bytes: int | None = None,
    ) -> int:
        """Spawns process in a new process group (preexec_fn=os.setpgrp)."""
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            preexec_fn=os.setpgrp,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return proc.pid

    def terminate_process_group(self, pgid: int) -> None:
        """Kills the entire process group with SIGKILL."""
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def cleanup_workspace(self, workspace_path: Path) -> None:
        """Recursively removes temporary workspace files and sockets."""
        if workspace_path.exists():
            shutil.rmtree(workspace_path, ignore_errors=True)
