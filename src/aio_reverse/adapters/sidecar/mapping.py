"""Maps sidecar protocol errors onto aio_reverse domain errors."""

from __future__ import annotations

from aio_sidecar import ErrorKind, WreError

from aio_reverse.domain.errors import (
    AioReverseError,
    EmulationFailureError,
    SandboxResourceLimitError,
    TimeoutError,
)


def _message(error: WreError) -> str:
    op = error.op or "call"
    return f"sidecar {op} failed ({error.kind}): {error.message}"


def map_sidecar_error(error: WreError) -> AioReverseError:
    """Returns the domain error matching *error*'s taxonomy kind.

    ``timeout``/``cancelled`` become ``TimeoutError``, ``resource`` becomes
    ``SandboxResourceLimitError`` and everything else is an
    ``EmulationFailureError``. Callers re-raise with ``from error``.
    """
    if error.kind in (ErrorKind.TIMEOUT, ErrorKind.CANCELLED):
        return TimeoutError(_message(error))
    if error.kind == ErrorKind.RESOURCE:
        return SandboxResourceLimitError(_message(error))
    return EmulationFailureError(_message(error))
