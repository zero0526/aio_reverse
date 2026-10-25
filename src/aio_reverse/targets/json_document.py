"""Strict loading helpers for JSON configuration documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def load_json_object(path: Path, *, context: str) -> dict[str, Any]:
    """Load a file that must contain a single JSON object."""
    if not path.is_file():
        raise FileNotFoundError(f"{context}: no file at {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise OSError(f"{context}: could not read {path}") from error

    if not text.strip():
        raise ValueError(f"{context}: {path} is empty")

    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{context}: {path} is not valid JSON: {error}") from error

    if not isinstance(value, dict):
        raise ValueError(
            f"{context}: {path} must contain a JSON object, got {type(value).__name__}"
        )
    return value


def reject_unknown_keys(
    document: Mapping[str, Any],
    allowed: Iterable[str],
    *,
    context: str,
) -> None:
    allowed_keys = set(allowed)
    unknown = sorted(set(document) - allowed_keys)
    if unknown:
        raise ValueError(
            f"{context}: unknown keys {unknown}; allowed keys: {sorted(allowed_keys)}"
        )


def require_string(document: Mapping[str, Any], key: str, *, context: str) -> str:
    if key not in document:
        raise ValueError(f"{context}: missing required key {key!r}")
    value = document[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: {key!r} must be a non-empty string")
    return value


def optional_string(
    document: Mapping[str, Any], key: str, *, context: str
) -> str | None:
    value = document.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: {key!r} must be a non-empty string when present")
    return value


def optional_string_list(document: Mapping[str, Any], key: str, *, context: str) -> tuple[str, ...]:
    value = document.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{context}: {key!r} must be a list of strings")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"{context}: {key}[{index}] must be a non-empty string, got {item!r}"
            )
        items.append(item.strip())
    return tuple(items)


def require_integer(document: Mapping[str, Any], key: str, *, context: str) -> int:
    if key not in document:
        raise ValueError(f"{context}: missing required key {key!r}")
    return _as_integer(document[key], key, context)


def optional_integer(
    document: Mapping[str, Any],
    key: str,
    *,
    context: str,
    default: int,
) -> int:
    if key not in document:
        return default
    return _as_integer(document[key], key, context)


def optional_number(
    document: Mapping[str, Any],
    key: str,
    *,
    context: str,
    default: float | None = None,
) -> float | None:
    if key not in document:
        return default
    value = document[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context}: {key!r} must be a number, got {value!r}")
    return float(value)


def optional_boolean(
    document: Mapping[str, Any],
    key: str,
    *,
    context: str,
    default: bool,
) -> bool:
    if key not in document:
        return default
    value = document[key]
    if not isinstance(value, bool):
        raise ValueError(f"{context}: {key!r} must be true or false, got {value!r}")
    return value


def _as_integer(value: Any, key: str, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context}: {key!r} must be an integer, got {value!r}")
    return value
