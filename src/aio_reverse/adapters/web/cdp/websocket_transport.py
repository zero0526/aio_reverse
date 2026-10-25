"""Synchronous WebSocket transport for the Chrome DevTools Protocol."""

from __future__ import annotations

import threading
from typing import Protocol

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from aio_reverse.domain.errors import BrowserSessionError


class WsTransport(Protocol):
    def send(self, message: str) -> None: ...

    def recv(self) -> str: ...

    def close(self) -> None: ...


class WebSocketTransport:
    """Thin synchronous websocket transport with contextual errors."""

    def __init__(self, url: str) -> None:
        self.url = url
        try:
            self._connection = connect(
                url, open_timeout=10, close_timeout=2, max_size=None
            )
        except (OSError, WebSocketException) as error:
            raise BrowserSessionError(
                f"cannot open CDP websocket {url}: {error}"
            ) from error
        self._send_lock = threading.Lock()

    def send(self, message: str) -> None:
        with self._send_lock:
            try:
                self._connection.send(message)
            except (OSError, WebSocketException) as error:
                raise BrowserSessionError(
                    f"failed to send to CDP websocket {self.url}: {error}"
                ) from error

    def recv(self) -> str:
        try:
            message = self._connection.recv()
        except (OSError, WebSocketException) as error:
            raise BrowserSessionError(
                f"failed to receive from CDP websocket {self.url}: {error}"
            ) from error
        if isinstance(message, bytes):
            try:
                return message.decode("utf-8")
            except UnicodeDecodeError as error:
                raise BrowserSessionError(
                    f"CDP websocket {self.url} sent non UTF-8 data"
                ) from error
        return message

    def close(self) -> None:
        try:
            self._connection.close()
        except (OSError, WebSocketException) as error:
            raise BrowserSessionError(
                f"failed to close CDP websocket {self.url}: {error}"
            ) from error
