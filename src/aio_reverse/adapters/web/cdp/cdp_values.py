"""Typed accessors for values carried by Chrome DevTools Protocol events."""

from __future__ import annotations

from typing import Any

from aio_reverse.domain.errors import BrowserSessionError

SENSITIVE_HEADERS = frozenset(
    {"cookie", "set-cookie", "authorization", "proxy-authorization"}
)
REDACTED_VALUE = "[redacted]"


def required_str(source: dict[str, Any], key: str, method: str) -> str:
    value = source.get(key)
    if not isinstance(value, str):
        raise BrowserSessionError(
            f"{method} is missing the string field {key!r}"
        )
    return value


def optional_str(source: dict[str, Any], key: str) -> str | None:
    value = source.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise BrowserSessionError(
            f"field {key!r} is {type(value).__name__}, expected a string"
        )
    return value


def optional_number(
    source: dict[str, Any], key: str, method: str
) -> float | None:
    value = source.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrowserSessionError(f"{method} has a non-numeric {key!r}")
    return float(value)


def optional_bool(source: dict[str, Any], key: str) -> bool | None:
    value = source.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise BrowserSessionError(
            f"field {key!r} is {type(value).__name__}, expected a boolean"
        )
    return value


def header_map(value: Any, method: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise BrowserSessionError(f"{method} has non-object headers")
    return {
        str(key): (
            REDACTED_VALUE
            if str(key).strip().lower() in SENSITIVE_HEADERS
            else str(item)
        )
        for key, item in value.items()
    }


def initiator_type(params: dict[str, Any]) -> str | None:
    initiator = params.get("initiator")
    if initiator is None:
        return None
    if not isinstance(initiator, dict):
        raise BrowserSessionError("Network.requestWillBeSent has bad initiator")
    return optional_str(initiator, "type")


def initiator_url(params: dict[str, Any]) -> str | None:
    initiator = params.get("initiator")
    if not isinstance(initiator, dict):
        return None
    stack = initiator.get("stack")
    if not isinstance(stack, dict):
        return None
    frames = stack.get("callFrames")
    if not isinstance(frames, list) or not frames:
        return None
    first = frames[0]
    if not isinstance(first, dict):
        return None
    return optional_str(first, "url")


def remote_value(value: Any, method: str) -> Any:
    if not isinstance(value, dict):
        raise BrowserSessionError(f"{method} has a non-object console arg")
    if "value" in value:
        return value["value"]
    if "unserializableValue" in value:
        return value["unserializableValue"]
    return value.get("description")


def call_frames(stack: Any, method: str) -> list[dict[str, Any]]:
    if stack is None:
        return []
    if not isinstance(stack, dict):
        raise BrowserSessionError(f"{method} has a non-object stack")
    frames = stack.get("callFrames", [])
    if not isinstance(frames, list):
        raise BrowserSessionError(f"{method} stack has no callFrames list")
    return [
        {
            "function": frame.get("functionName"),
            "url": frame.get("url"),
            "line": frame.get("lineNumber"),
            "column": frame.get("columnNumber"),
        }
        for frame in frames
        if isinstance(frame, dict)
    ]
