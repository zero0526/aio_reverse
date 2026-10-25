"""Long-lived web sessions shared by MCP tool calls."""

from __future__ import annotations

import threading
from typing import Callable

from aio_reverse.application.ports.web_session_port import IWebSession
from aio_reverse.domain.errors import BrowserSessionError
from aio_reverse.targets.target_registry import TargetRegistry
from aio_reverse.targets.web_target import WebTargetSpec


class SessionRegistry:
    """Keeps at most one session per target and closes them deterministically."""

    def __init__(
        self,
        targets: TargetRegistry,
        factory: Callable[[WebTargetSpec], IWebSession],
    ) -> None:
        self._targets = targets
        self._factory = factory
        self._sessions: dict[str, IWebSession] = {}
        self._lock = threading.Lock()

    def acquire(self, target_name: str) -> IWebSession:
        """Return the live session, creating it once under the lock."""
        with self._lock:
            existing = self._sessions.get(target_name)
            if existing is not None:
                return existing
            target = self._targets.resolve(target_name)
            session = self._factory(target)
            self._sessions[target_name] = session
            return session

    def close(self, target_name: str, keep_browser: bool = True) -> bool:
        """Drop one session; return False when it was not open."""
        with self._lock:
            session = self._sessions.pop(target_name, None)
        if session is None:
            return False
        session.close(keep_browser=keep_browser)
        return True

    def close_all(self) -> None:
        """Close every live session, reporting the first failure after trying all."""
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        failed = 0
        first_error: Exception | None = None
        for session in sessions:
            try:
                session.close(keep_browser=True)
            except Exception as error:
                failed += 1
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise BrowserSessionError(
                f"failed to close {failed} of {len(sessions)} web session(s)"
            ) from first_error
