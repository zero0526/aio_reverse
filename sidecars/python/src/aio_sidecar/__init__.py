"""Python SDK for aio_reverse sidecar engines (wire protocol v1)."""

from .alerts import ALERT_PHASES, AlertHandler, EventHook, SidecarAlert, SidecarEvent
from .client import SidecarClient, SidecarSession, connect
from .errors import (
    RETRYABLE_KINDS,
    BadInput,
    Blocked,
    Cancelled,
    ErrorKind,
    InternalError,
    ProtocolError,
    ResourceError,
    SidecarError,
    TargetDrift,
    Timeout,
    Unsupported,
    WreError,
    error_from_wire,
)
from .hash import canonical_json, fnv1a64, schema_hash

__all__ = [
    "ALERT_PHASES",
    "AlertHandler",
    "BadInput",
    "Blocked",
    "Cancelled",
    "ErrorKind",
    "EventHook",
    "InternalError",
    "ProtocolError",
    "RETRYABLE_KINDS",
    "ResourceError",
    "SidecarAlert",
    "SidecarClient",
    "SidecarError",
    "SidecarEvent",
    "SidecarSession",
    "TargetDrift",
    "Timeout",
    "Unsupported",
    "WreError",
    "canonical_json",
    "connect",
    "error_from_wire",
    "fnv1a64",
    "schema_hash",
]
