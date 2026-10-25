"""Polling helpers for page expressions used by action scripts."""

from __future__ import annotations

import time
from typing import Any, Callable

from aio_reverse.application.page_element_expressions import (
    visible_absence_expression,
    visible_count_expression,
    visible_presence_expression,
)
from aio_reverse.application.ports.browser_session_port import IBrowserSessionPort
from aio_reverse.domain.errors import BrowserSessionError, FlowTimeoutError

POLL_S = 0.1


class ExpressionWaiter:
    """Polls page state until a condition holds, failing loud on timeout."""

    def __init__(
        self,
        session: IBrowserSessionPort,
        poll_s: float = POLL_S,
    ) -> None:
        if poll_s <= 0:
            raise ValueError(f"poll_s must be positive, got {poll_s}")
        self._session = session
        self._poll_s = poll_s

    def wait_truthy(
        self,
        expression: str,
        timeout_s: float,
        *,
        context: str,
    ) -> None:
        self._require_timeout(timeout_s, context)
        self._poll(
            expression,
            timeout_s,
            lambda value: value is True,
            context,
        )

    def wait_visible(self, selector: str, timeout_s: float = 60.0) -> None:
        self._require_timeout(timeout_s, f"wait_visible {selector!r}")
        self._poll(
            visible_presence_expression(selector),
            timeout_s,
            lambda value: value is True,
            f"wait_visible {selector!r}",
        )

    def wait_hidden(self, selector: str, timeout_s: float = 60.0) -> None:
        self._require_timeout(timeout_s, f"wait_hidden {selector!r}")
        self._poll(
            visible_absence_expression(selector),
            timeout_s,
            lambda value: value is True,
            f"wait_hidden {selector!r}",
        )

    def count(self, selector: str, timeout_s: float = 30.0) -> int:
        self._require_timeout(timeout_s, f"count {selector!r}")
        expression = visible_count_expression(selector)
        value = self._session.evaluate(expression, timeout_s=timeout_s)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BrowserSessionError(
                f"count {selector!r} returned {value!r}, expected a non-negative integer"
            )
        return value

    def wait_count(
        self,
        selector: str,
        greater_than: int,
        timeout_s: float = 60.0,
    ) -> None:
        context = f"wait_count {selector!r} > {greater_than}"
        self._require_timeout(timeout_s, context)
        self._poll(
            visible_count_expression(selector),
            timeout_s,
            lambda value: self._is_count_above(value, greater_than),
            context,
        )

    def wait_network_quiet(self, ms: int, timeout_s: float = 30.0) -> None:
        if ms <= 0:
            raise ValueError(f"ms must be positive, got {ms}")
        self._require_timeout(timeout_s, "wait_network_quiet")
        deadline = time.monotonic() + timeout_s
        quiet_s = ms / 1000.0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FlowTimeoutError(
                    f"network did not stay quiet for {ms}ms within {timeout_s}s"
                )
            idle = time.monotonic() - self._session.last_network_activity()
            if idle >= quiet_s:
                return
            time.sleep(min(self._poll_s, remaining))

    def _poll(
        self,
        expression: str,
        timeout_s: float,
        predicate: Callable[[Any], bool],
        context: str,
    ) -> None:
        deadline = time.monotonic() + timeout_s
        last_error: BrowserSessionError | None = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                value = self._session.evaluate(
                    expression, timeout_s=min(10.0, remaining)
                )
            except BrowserSessionError as error:
                last_error = error
            else:
                if predicate(value):
                    return
            time.sleep(min(self._poll_s, remaining))
        raise FlowTimeoutError(
            f"{context} did not hold within {timeout_s}s"
        ) from last_error

    @staticmethod
    def _is_count_above(value: Any, greater_than: int) -> bool:
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        return value > greater_than

    @staticmethod
    def _require_timeout(timeout_s: float, context: str) -> None:
        if timeout_s <= 0:
            raise ValueError(f"{context}: timeout_s must be positive, got {timeout_s}")
