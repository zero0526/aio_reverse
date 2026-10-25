"""Builds per-turn and per-run summaries written to run artifacts."""

from __future__ import annotations

from typing import Any, Sequence

from aio_reverse.application.ports.web_session_port import RunPaths, SessionTurn
from aio_reverse.targets.web_target import WebTargetSpec

PROBE_LIST_FIELDS = ("reads", "calls", "events", "network", "sse", "websocket")


def summarise_turn(
    index: int,
    target: WebTargetSpec,
    turn: SessionTurn,
) -> dict[str, Any]:
    """Return the compact record of one executed action script."""
    requests = turn.capture.requests
    matched = [
        request
        for request in requests
        if _matches_url(request.get("url"), target.network_patterns)
    ]
    probe = turn.probe
    probe_counts = {
        field: len(_probe_list(probe, field, index))
        for field in PROBE_LIST_FIELDS
    }
    return {
        "index": index,
        "script": turn.script,
        "variables": turn.variables,
        "steps": len(turn.steps),
        "duration_s": turn.duration_s,
        "requests": len(requests),
        "matched_requests": [
            {
                "method": request.get("method"),
                "url": request.get("url"),
                "status": request.get("status"),
                "body_bytes": request.get("body_bytes"),
            }
            for request in matched
        ],
        "sse_events": len(turn.capture.sse_events),
        "ws_frames": len(turn.capture.ws_frames),
        "console_errors": sum(
            1
            for line in turn.capture.console
            if line.get("type") in ("error", "assert")
        ),
        "exceptions": len(turn.capture.exceptions),
        "probe": {
            **probe_counts,
            "top_reads": _top_entries(
                _probe_list(probe, "reads", index), index
            ),
            "top_calls": _top_entries(
                _probe_list(probe, "calls", index), index
            ),
        },
    }


def summarise_run(
    paths: RunPaths,
    target: WebTargetSpec,
    turns: Sequence[dict[str, Any]],
    setup_scripts: Sequence[str],
    setup_steps: int,
) -> dict[str, Any]:
    """Return the cross-turn summary for one run."""
    totals: dict[str, Any] = {
        "turns": len(turns),
        "steps": sum(turn["steps"] for turn in turns),
        "requests": sum(turn["requests"] for turn in turns),
        "matched_requests": sum(
            len(turn["matched_requests"]) for turn in turns
        ),
        "sse_events": sum(turn["sse_events"] for turn in turns),
        "ws_frames": sum(turn["ws_frames"] for turn in turns),
        "console_errors": sum(turn["console_errors"] for turn in turns),
        "exceptions": sum(turn["exceptions"] for turn in turns),
        "duration_s": sum(turn["duration_s"] for turn in turns),
        "probe": {
            field: sum(turn["probe"][field] for turn in turns)
            for field in PROBE_LIST_FIELDS
        },
    }
    return {
        "run_id": paths.run_id,
        "target": target.name,
        "entry_url": target.entry_url,
        "patterns": list(target.network_patterns),
        "setup_scripts": list(setup_scripts),
        "setup_steps": setup_steps,
        "turns": list(turns),
        "totals": totals,
    }


def _matches_url(url: Any, patterns: Sequence[str]) -> bool:
    return isinstance(url, str) and any(
        pattern in url for pattern in patterns
    )


def _probe_list(
    probe: dict[str, Any], field: str, turn_index: int
) -> list[Any]:
    value = probe.get(field, [])
    if not isinstance(value, list):
        raise TypeError(
            f"turn {turn_index} probe field {field!r} is "
            f"{type(value).__name__}, expected a list"
        )
    return value


def _top_entries(
    entries: Sequence[Any], turn_index: int
) -> list[dict[str, Any]]:
    ordered = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError(
                f"turn {turn_index} probe entry is "
                f"{type(entry).__name__}, expected an object"
            )
        key = entry.get("key")
        count = entry.get("count")
        if not isinstance(key, str) or not isinstance(count, int):
            raise TypeError(
                f"turn {turn_index} probe entry has no string key/int count"
            )
        ordered.append({"key": key, "count": count})
    ordered.sort(key=lambda item: item["count"], reverse=True)
    return ordered[:5]
