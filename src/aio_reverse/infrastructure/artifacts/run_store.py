"""Filesystem artifact store for scripted web runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aio_reverse.application.ports.web_session_port import (
    IRunStore,
    RunPaths,
    SessionTurn,
)
from aio_reverse.infrastructure.artifacts.artifact_naming import safe_name, utc_stamp


class RunStore(IRunStore):
    """Writes run, turn and summary JSON under ``data/output/web``."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def create_run(self, target_name: str) -> RunPaths:
        stamp = utc_stamp()
        run_id = f"{stamp}-{safe_name(target_name)}"
        run_dir = self.root / safe_name(target_name) / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        return RunPaths(run_id=run_id, run_dir=run_dir)

    def write_run(self, paths: RunPaths, payload: dict[str, Any]) -> None:
        self._write_json(paths.run_dir / "run.json", payload)

    def write_summary(self, paths: RunPaths, payload: dict[str, Any]) -> None:
        self._write_json(paths.run_dir / "summary.json", payload)

    def write_turn(self, paths: RunPaths, index: int, turn: SessionTurn) -> None:
        turn_dir = paths.run_dir / f"turn-{index:02d}"
        turn_dir.mkdir(parents=True, exist_ok=False)

        self._write_json(
            turn_dir / "request.json",
            {"script": turn.script, "variables": turn.variables},
        )
        self._write_json(
            turn_dir / "steps.json",
            [step.to_dict() for step in turn.steps],
        )
        self._write_json(turn_dir / "probe.json", turn.probe)
        self._write_json(
            turn_dir / "network.json",
            {
                "started_at": turn.capture.started_at,
                "ended_at": turn.capture.ended_at,
                "requests": turn.capture.requests,
            },
        )
        self._write_json(turn_dir / "sse.json", turn.capture.sse_events)
        self._write_json(turn_dir / "websocket.json", turn.capture.ws_frames)
        self._write_json(turn_dir / "console.json", turn.capture.console)
        self._write_json(turn_dir / "exceptions.json", turn.capture.exceptions)
        self._write_json(turn_dir / "env.json", turn.env)
        self._write_json(turn_dir / "page.json", turn.page)
        self._write_json(
            turn_dir / "timings.json",
            {
                "started_at": turn.started_at,
                "ended_at": turn.ended_at,
                "duration_s": turn.duration_s,
                "steps": [
                    {
                        "index": step.index,
                        "type": step.type,
                        "duration_s": step.ended_at - step.started_at,
                    }
                    for step in turn.steps
                ],
            },
        )

    def _write_json(self, path: Path, payload: Any) -> None:
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
