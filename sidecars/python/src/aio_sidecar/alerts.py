"""Alert and event payloads delivered by the sidecar SDK."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

_LOGGER = logging.getLogger("aio_sidecar")

ALERT_PHASES = ("connect", "call", "close")


def utc_now() -> str:
    """Returns an ISO-8601 UTC timestamp for alert payloads."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SidecarAlert:
    """A typed sidecar failure observed by the SDK.

    ``exception`` is the original ``WreError`` instance that will be (or has
    been) raised; the alert is always emitted before the exception propagates.
    """

    kind: str
    message: str
    retryable: bool
    phase: str
    client_id: Optional[str]
    target: Optional[str]
    op: Optional[str]
    session: Optional[str]
    binary: str
    pid: Optional[int]
    detail: Any
    exception: BaseException
    occurred_at: str


@dataclass(frozen=True)
class SidecarEvent:
    """An engine event; enriched when routed to a per-call handler."""

    call_id: int
    event: str
    data: Any
    client_id: Optional[str] = None
    target: Optional[str] = None
    op: Optional[str] = None
    session: Optional[str] = None


AlertHandler = Callable[[SidecarAlert], None]
EventHook = Callable[[SidecarEvent], None]


def emit_alert(alert: SidecarAlert, handler: Optional[AlertHandler]) -> None:
    """Delivers *alert* to *handler*, or logs it when no handler is configured.

    A failing handler is logged and never masks the original sidecar error.
    """
    if handler is None:
        _LOGGER.error(
            "sidecar alert kind=%s phase=%s target=%s op=%s session=%s "
            "binary=%s pid=%s retryable=%s: %s",
            alert.kind,
            alert.phase,
            alert.target,
            alert.op,
            alert.session,
            alert.binary,
            alert.pid,
            alert.retryable,
            alert.message,
        )
        return
    try:
        handler(alert)
    except Exception:
        _LOGGER.exception(
            "sidecar alert handler failed for kind=%s phase=%s target=%s op=%s",
            alert.kind,
            alert.phase,
            alert.target,
            alert.op,
        )
