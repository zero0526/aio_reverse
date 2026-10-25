"""Applies the artifact body policy to Rust probe network records."""

from __future__ import annotations

from typing import Any, Sequence


def redact_probe_network(
    probe: dict[str, Any], body_capture_patterns: Sequence[str]
) -> dict[str, Any]:
    """Drop raw probe body samples unless the URL is allowed to keep them."""
    entries = probe.get("network")
    if not isinstance(entries, list):
        raise ValueError(
            "probe.network must be a list, got "
            f"{type(entries).__name__}"
        )
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(
                f"probe.network[{index}] must be an object, got "
                f"{type(entry).__name__}"
            )
        body = entry.get("body")
        if body is None:
            continue
        if not isinstance(body, str):
            raise ValueError(
                f"probe.network[{index}].body must be a string, got "
                f"{type(body).__name__}"
            )
        url = entry.get("url")
        if not isinstance(url, str):
            raise ValueError(
                f"probe.network[{index}].url must be a string, got "
                f"{type(url).__name__}"
            )
        if any(pattern in url for pattern in body_capture_patterns):
            continue
        entry["body"] = None
        entry["body_redacted"] = True
    return probe
