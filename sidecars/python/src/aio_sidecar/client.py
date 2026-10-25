"""Sidecar client and session wrappers with alert/event callbacks."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Mapping, Optional, Sequence

from wre_runtime.errors import ResourceError, WreError
from wre_runtime.sidecar import Session as _RuntimeSession
from wre_runtime.sidecar import Sidecar as _RuntimeSidecar
from wre_runtime.sidecar import connect as _runtime_connect

from .alerts import (
    AlertHandler,
    EventHook,
    SidecarAlert,
    SidecarEvent,
    emit_alert,
    utc_now,
)

_LOGGER = logging.getLogger("aio_sidecar")

_RuntimeEventHandler = Callable[[int, str, Any], None]


def connect(
    binary: str,
    *,
    args: Sequence[str] = (),
    client_id: Optional[str] = None,
    on_alert: Optional[AlertHandler] = None,
    on_event: Optional[EventHook] = None,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[str] = None,
    stderr: str = "ignore",
    expect_schema_hash: Optional[str] = None,
    startup_timeout: float = 30.0,
) -> "SidecarClient":
    """Spawns *binary* and performs the protocol v1 handshake.

    Spawn failures surface as a retryable ``ResourceError`` and fire an alert
    with ``phase="connect"`` before the exception is raised.
    """
    global_event = _make_global_event_handler(client_id, on_event)

    try:
        runtime = _runtime_connect(
            binary,
            args=tuple(args),
            env=env,
            cwd=cwd,
            stderr=stderr,
            on_event=global_event,
            expect_protocol=1,
            expect_schema_hash=expect_schema_hash,
            startup_timeout=startup_timeout,
        )
    except WreError as exc:
        emit_alert(_connect_alert(binary, client_id, exc), on_alert)
        raise
    except OSError as exc:
        error = ResourceError(
            f"failed to spawn sidecar {binary!r}: {exc}",
            retryable=True,
            op="hello",
            detail={"errno": exc.errno},
        )
        emit_alert(_connect_alert(binary, client_id, error), on_alert)
        raise error from exc

    return SidecarClient(
        runtime,
        binary=binary,
        client_id=client_id,
        on_alert=on_alert,
        on_event=on_event,
    )


class SidecarClient:
    """A live sidecar process speaking wire protocol v1."""

    def __init__(
        self,
        runtime: _RuntimeSidecar,
        *,
        binary: str,
        client_id: Optional[str],
        on_alert: Optional[AlertHandler],
        on_event: Optional[EventHook],
    ) -> None:
        self._runtime = runtime
        self._binary = binary
        self._client_id = client_id
        self._on_alert = on_alert
        self._on_event = on_event
        self._lock = threading.RLock()
        self._sessions: dict[str, SidecarSession] = {}
        self._closed = False

    @property
    def hello(self) -> dict[str, Any]:
        return self._runtime.hello

    @property
    def pid(self) -> int:
        return self._runtime.pid

    @property
    def binary(self) -> str:
        return self._binary

    @property
    def client_id(self) -> Optional[str]:
        return self._client_id

    def describe(self) -> dict[str, Any]:
        return self._guard("call", None, "describe", None, self._runtime.describe)

    def targets(self) -> list[str]:
        result = self._guard("call", None, "targets", None, self._runtime.targets)
        return list(result)

    def metrics(self) -> dict[str, Any]:
        return self._guard("call", None, "metrics", None, self._runtime.metrics)

    def open(
        self, target: str, config: Optional[Mapping[str, Any]] = None
    ) -> "SidecarSession":

        def do_open() -> _RuntimeSession:
            payload = dict(config) if config is not None else None
            return self._runtime.open(target, payload)

        runtime_session = self._guard("call", target, "open", None, do_open)
        session = SidecarSession(self, runtime_session)
        with self._lock:
            self._sessions[runtime_session.id] = session
        return session

    def call(
        self,
        op: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        session: Optional[Any] = None,
        deadline_ms: Optional[int] = None,
        on_event: Optional[EventHook] = None,
        bin_part: bytes = b"",
    ) -> Any:
        result, _ = self.call_with_binary(
            op,
            params,
            session=session,
            deadline_ms=deadline_ms,
            on_event=on_event,
            bin_part=bin_part,
        )
        return result

    def call_with_binary(
        self,
        op: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        session: Optional[Any] = None,
        deadline_ms: Optional[int] = None,
        on_event: Optional[EventHook] = None,
        bin_part: bytes = b"",
    ) -> tuple[Any, bytes]:
        if isinstance(session, SidecarSession):
            return session.call_with_binary(
                op,
                params,
                deadline_ms=deadline_ms,
                on_event=on_event,
                bin_part=bin_part,
            )

        target = self._target_for(session)
        return self._invoke(
            op,
            params,
            session_id=session,
            target=target,
            deadline_ms=deadline_ms,
            on_event=on_event,
            bin_part=bin_part,
        )

    def close(self) -> None:
        """Kills the sidecar process and marks all sessions closed."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session._mark_closed()
        self._runtime.close()
        self._close_stdio()

    def _close_stdio(self) -> None:
        # wre_runtime kills the child but leaves its pipes open; closing them
        # here avoids leaking one file descriptor per connection.
        proc = getattr(self._runtime, "_proc", None)
        for stream in (
            getattr(proc, "stdout", None),
            getattr(proc, "stderr", None),
        ):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass

    def shutdown(self) -> None:
        """Asks the engine to shut down, then closes the process.

        Failures are reported through the alert callback and then swallowed so
        cleanup can complete.
        """
        with self._lock:
            if self._closed:
                return
        try:
            self._invoke(
                "shutdown",
                {},
                session_id=None,
                target=None,
                deadline_ms=5000,
                on_event=None,
                bin_part=b"",
                phase="close",
            )
        except WreError:
            pass
        finally:
            self.close()

    def __enter__(self) -> "SidecarClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _target_for(self, session_id: Optional[str]) -> Optional[str]:
        if session_id is None:
            return None
        with self._lock:
            session = self._sessions.get(session_id)
        return session.target if session is not None else None

    def _invoke(
        self,
        op: str,
        params: Optional[Mapping[str, Any]],
        *,
        session_id: Optional[str],
        target: Optional[str],
        deadline_ms: Optional[int],
        on_event: Optional[EventHook],
        bin_part: bytes,
        phase: str = "call",
    ) -> tuple[Any, bytes]:
        deadline = None if deadline_ms is None else deadline_ms / 1000.0
        runtime_event = _make_call_event_handler(
            self._client_id, target, op, session_id, on_event
        )

        def do_call() -> tuple[Any, bytes]:
            return self._runtime.call_with_binary(
                op,
                dict(params) if params is not None else {},
                session=session_id,
                deadline=deadline,
                on_event=runtime_event,
                bin_part=bin_part,
            )

        return self._guard(phase, target, op, session_id, do_call)

    def _guard(
        self,
        phase: str,
        target: Optional[str],
        op: Optional[str],
        session: Optional[str],
        fn: Callable[[], Any],
    ) -> Any:
        try:
            return fn()
        except WreError as exc:
            self._emit_alert(phase, target, op, session, exc)
            raise
        except OSError as exc:
            error = ResourceError(
                f"{op} failed: {exc}",
                retryable=True,
                target=target,
                op=op,
                detail={"errno": exc.errno},
            )
            self._emit_alert(phase, target, op, session, error)
            raise error from exc

    def _emit_alert(
        self,
        phase: str,
        target: Optional[str],
        op: Optional[str],
        session: Optional[str],
        error: WreError,
    ) -> None:
        alert = SidecarAlert(
            kind=error.kind,
            message=error.message,
            retryable=error.retryable,
            phase=phase,
            client_id=self._client_id,
            target=error.target if error.target is not None else target,
            op=error.op if error.op is not None else op,
            session=session,
            binary=self._binary,
            pid=self.pid,
            detail=error.detail,
            exception=error,
            occurred_at=utc_now(),
        )
        emit_alert(alert, self._on_alert)


class SidecarSession:
    """An open engine session; calls are routed through the owning client."""

    def __init__(self, client: SidecarClient, runtime: _RuntimeSession) -> None:
        self._client = client
        self._runtime = runtime
        self._closed = False

    @property
    def id(self) -> str:
        return self._runtime.id

    @property
    def target(self) -> str:
        return self._runtime.target

    @property
    def ops(self) -> list[str]:
        return list(self._runtime.ops)

    def call(
        self,
        op: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        deadline_ms: Optional[int] = None,
        on_event: Optional[EventHook] = None,
    ) -> Any:
        result, _ = self.call_with_binary(
            op, params, deadline_ms=deadline_ms, on_event=on_event
        )
        return result

    def call_with_binary(
        self,
        op: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        deadline_ms: Optional[int] = None,
        on_event: Optional[EventHook] = None,
        bin_part: bytes = b"",
    ) -> tuple[Any, bytes]:
        return self._client._invoke(
            op,
            params,
            session_id=self.id,
            target=self.target,
            deadline_ms=deadline_ms,
            on_event=on_event,
            bin_part=bin_part,
        )

    def health(self) -> Any:
        return self.call("health", {})

    def warmup(self) -> Any:
        return self.call("warmup", {})

    def close(self) -> None:
        """Closes the session; wire failures are alerted and then swallowed."""
        if self._closed:
            return
        self._closed = True
        try:
            self._client._invoke(
                "close",
                {},
                session_id=self.id,
                target=self.target,
                deadline_ms=None,
                on_event=None,
                bin_part=b"",
                phase="close",
            )
        except WreError:
            pass
        finally:
            with self._client._lock:
                self._client._sessions.pop(self.id, None)

    def __enter__(self) -> "SidecarSession":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _mark_closed(self) -> None:
        self._closed = True


def _make_global_event_handler(
    client_id: Optional[str], on_event: Optional[EventHook]
) -> Optional[_RuntimeEventHandler]:
    if on_event is None:
        return None

    def handler(call_id: int, event: str, data: Any) -> None:
        try:
            on_event(
                SidecarEvent(
                    call_id=call_id,
                    event=event,
                    data=data,
                    client_id=client_id,
                )
            )
        except Exception:
            _LOGGER.exception(
                "sidecar global event handler failed for call %s event %s",
                call_id,
                event,
            )

    return handler


def _make_call_event_handler(
    client_id: Optional[str],
    target: Optional[str],
    op: str,
    session_id: Optional[str],
    on_event: Optional[EventHook],
) -> Optional[_RuntimeEventHandler]:
    if on_event is None:
        return None

    def handler(call_id: int, event: str, data: Any) -> None:
        try:
            on_event(
                SidecarEvent(
                    call_id=call_id,
                    event=event,
                    data=data,
                    client_id=client_id,
                    target=target,
                    op=op,
                    session=session_id,
                )
            )
        except Exception:
            _LOGGER.exception(
                "sidecar event handler failed for %s.%s", target, op
            )

    return handler


def _connect_alert(
    binary: str, client_id: Optional[str], error: WreError
) -> SidecarAlert:
    return SidecarAlert(
        kind=error.kind,
        message=error.message,
        retryable=error.retryable,
        phase="connect",
        client_id=client_id,
        target=error.target,
        op=error.op if error.op is not None else "hello",
        session=None,
        binary=binary,
        pid=None,
        detail=error.detail,
        exception=error,
        occurred_at=utc_now(),
    )
