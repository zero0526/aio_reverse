"""Execution sandbox backed by an out-of-process sidecar engine."""

from __future__ import annotations

import threading
from typing import Any, Mapping, Optional, Sequence

from aio_sidecar import (
    AlertHandler,
    ErrorKind,
    EventHook,
    SidecarClient,
    SidecarSession,
    WreError,
    connect,
)

from aio_reverse.application.ports.execution_sandbox_port import IExecutionSandboxPort
from aio_reverse.domain.errors import EmulationFailureError

from .mapping import map_sidecar_error

_TRANSPORT_KINDS = frozenset({ErrorKind.PROTOCOL, ErrorKind.RESOURCE})


class SidecarSandboxAdapter(IExecutionSandboxPort):
    """Runs reversed code through any host SDK speaking wire protocol v1.

    The child process is spawned lazily on the first ``execute_snippet`` and
    kept for later calls. Transport failures drop the client so the next call
    reconnects with a fresh process.
    """

    def __init__(
        self,
        binary: str,
        *,
        args: Sequence[str] = (),
        target: str = "echo",
        op: str = "execute",
        client_id: Optional[str] = None,
        on_alert: Optional[AlertHandler] = None,
        on_event: Optional[EventHook] = None,
        env: Optional[Mapping[str, str]] = None,
        stderr: str = "ignore",
        default_deadline_ms: Optional[int] = None,
    ) -> None:
        self._binary = binary
        self._args = tuple(args)
        self._target = target
        self._op = op
        self._client_id = client_id
        self._on_alert = on_alert
        self._on_event = on_event
        self._env = env
        self._stderr = stderr
        self._default_deadline_ms = default_deadline_ms
        self._lock = threading.Lock()
        self._client: Optional[SidecarClient] = None
        self._session: Optional[SidecarSession] = None

    def execute_snippet(
        self,
        code_or_binary: str | bytes,
        entrypoint: str,
        arguments: list[Any],
        environment_shim: dict[str, Any] | None = None,
        timeout_ms: int = 1000,
        memory_limit_mb: int = 64,
    ) -> Any:
        if isinstance(code_or_binary, str):
            source_kind = "text"
            source: Optional[str] = code_or_binary
            bin_part = b""
        elif isinstance(code_or_binary, bytes):
            source_kind = "binary"
            source = None
            bin_part = code_or_binary
        else:
            raise TypeError(
                "code_or_binary must be str or bytes, got "
                f"{type(code_or_binary).__name__}"
            )

        params = {
            "entrypoint": entrypoint,
            "arguments": list(arguments),
            "environment": environment_shim,
            "source_kind": source_kind,
            "source": source,
            "memory_limit_mb": memory_limit_mb,
        }
        deadline_ms = (
            timeout_ms if timeout_ms is not None else self._default_deadline_ms
        )

        with self._lock:
            try:
                session = self._ensure_session()
                payload, _ = session.call_with_binary(
                    self._op,
                    params,
                    deadline_ms=deadline_ms,
                    bin_part=bin_part,
                )
            except WreError as error:
                if error.kind in _TRANSPORT_KINDS:
                    self._release()
                raise map_sidecar_error(error) from error

        if not isinstance(payload, dict) or "result" not in payload:
            raise EmulationFailureError(
                f"sidecar op {self._op!r} on target {self._target!r} "
                "returned no result"
            )
        return payload["result"]

    def close(self) -> None:
        with self._lock:
            self._release()

    def __enter__(self) -> "SidecarSandboxAdapter":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _ensure_session(self) -> SidecarSession:
        if self._session is not None:
            return self._session

        client = connect(
            self._binary,
            args=self._args,
            client_id=self._client_id,
            on_alert=self._on_alert,
            on_event=self._on_event,
            env=self._env,
            stderr=self._stderr,
        )
        try:
            session = client.open(self._target)
        except BaseException:
            client.close()
            raise
        self._client = client
        self._session = session
        return session

    def _release(self) -> None:
        client = self._client
        self._client = None
        self._session = None
        if client is not None:
            client.close()
