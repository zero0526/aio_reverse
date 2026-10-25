"""Multiplexes CDP commands and events over one transport connection."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from aio_reverse.adapters.web.cdp.websocket_transport import WsTransport
from aio_reverse.domain.errors import BrowserSessionError


@dataclass
class _Pending:
    event: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    timed_out: bool = False


class CdpChannel:
    """Multiplexes CDP commands and events over one websocket."""

    def __init__(
        self,
        transport: WsTransport,
        on_event: Callable[[dict[str, Any]], None],
    ) -> None:
        self._transport = transport
        self._on_event = on_event
        self._lock = threading.Lock()
        self._pending: dict[int, _Pending] = {}
        self._next_id = 0
        self._closed = False
        self._failure: BaseException | None = None
        self._reader = threading.Thread(
            target=self._read_loop, name="cdp-reader", daemon=True
        )
        self._reader.start()

    def ensure_usable(self) -> None:
        with self._lock:
            if self._failure is not None:
                failure = self._failure
            elif self._closed:
                raise BrowserSessionError("CDP channel is closed")
            else:
                return
        raise BrowserSessionError(f"CDP channel failed: {failure}") from failure

    def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        self.ensure_usable()

        with self._lock:
            self._next_id += 1
            command_id = self._next_id
            pending = _Pending()
            self._pending[command_id] = pending

        payload = json.dumps(
            {"id": command_id, "method": method, "params": params or {}}
        )
        try:
            self._transport.send(payload)
        except BaseException:
            with self._lock:
                self._pending.pop(command_id, None)
            raise

        if not pending.event.wait(timeout_s):
            with self._lock:
                pending.timed_out = True
            raise BrowserSessionError(f"{method} timed out after {timeout_s}s")

        if pending.error is not None:
            raise BrowserSessionError(
                f"{method} failed: {_error_text(pending.error)}"
            )
        if pending.result is None:
            raise BrowserSessionError(f"{method} returned no result")
        return pending.result

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            pending = list(self._pending.values())
            self._pending.clear()

        for item in pending:
            if not item.timed_out:
                item.error = {"code": -1, "message": "CDP channel closed"}
                item.event.set()

        try:
            self._transport.close()
        finally:
            self._reader.join(timeout=2.0)

    def _read_loop(self) -> None:
        try:
            while True:
                raw = self._transport.recv()
                if self._closed:
                    return
                self._dispatch(raw)
        except BaseException as error:
            if not self._closed:
                self._fail(error)

    def _dispatch(self, raw: str) -> None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as error:
            raise BrowserSessionError(
                f"invalid JSON from CDP: {raw[:200]}"
            ) from error
        if not isinstance(message, dict):
            raise BrowserSessionError(
                f"CDP message is {type(message).__name__}, expected an object"
            )

        if "id" in message:
            self._complete(message)
            return

        method = message.get("method")
        if not isinstance(method, str):
            raise BrowserSessionError(
                f"CDP message has neither a numeric id nor a method: {raw[:200]}"
            )
        params = message.get("params", {})
        if not isinstance(params, dict):
            raise BrowserSessionError(
                f"CDP event {method} has non-object params"
            )
        self._on_event({"method": method, "params": params})

    def _complete(self, message: dict[str, Any]) -> None:
        command_id = message.get("id")
        with self._lock:
            pending = self._pending.pop(command_id, None)
        if pending is None:
            raise BrowserSessionError(
                f"CDP response for unknown command id {command_id!r}"
            )
        if pending.timed_out:
            return

        if "error" in message:
            error = message["error"]
            pending.error = (
                error
                if isinstance(error, dict)
                else {"code": None, "message": str(error)}
            )
        else:
            result = message.get("result")
            if not isinstance(result, dict):
                pending.error = {
                    "code": None,
                    "message": f"response has no result object: {result!r}",
                }
            else:
                pending.result = result
        pending.event.set()

    def _fail(self, error: BaseException) -> None:
        with self._lock:
            if self._closed or self._failure is not None:
                return
            self._failure = error
            pending = list(self._pending.values())
            self._pending.clear()

        message = (
            str(error)
            if isinstance(error, BrowserSessionError)
            else f"{type(error).__name__}: {error}"
        )
        for item in pending:
            if not item.timed_out:
                item.error = {"code": -1, "message": message}
                item.event.set()


def _error_text(error: dict[str, Any]) -> str:
    code = error.get("code")
    message = error.get("message")
    data = error.get("data")
    text = f"{message} (code {code})" if code is not None else str(message)
    if data is not None:
        text = f"{text}: {data}"
    return text
