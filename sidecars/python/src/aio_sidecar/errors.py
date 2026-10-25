"""Typed sidecar errors.

The taxonomy is owned by ``wre_runtime`` and shared with every host; this
module only re-exports it under the sidecar SDK namespace.
"""

from wre_runtime.errors import (
    BadInput,
    Blocked,
    Cancelled,
    ErrorKind,
    InternalError,
    ProtocolError,
    ResourceError,
    TargetDrift,
    Timeout,
    Unsupported,
    WreError,
    error_from_wire,
)

SidecarError = WreError

RETRYABLE_KINDS = frozenset(
    {ErrorKind.BLOCKED, ErrorKind.TIMEOUT, ErrorKind.RESOURCE}
)

__all__ = [
    "BadInput",
    "Blocked",
    "Cancelled",
    "ErrorKind",
    "InternalError",
    "ProtocolError",
    "ResourceError",
    "RETRYABLE_KINDS",
    "SidecarError",
    "TargetDrift",
    "Timeout",
    "Unsupported",
    "WreError",
    "error_from_wire",
]
