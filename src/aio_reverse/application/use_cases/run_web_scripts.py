"""Use case: run setup and turn action scripts against one web target."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from aio_reverse.application.ports.web_session_port import (
    IRunStore,
    IWebSession,
    SessionTurn,
)
from aio_reverse.application.turn_summary import summarise_run, summarise_turn
from aio_reverse.targets.action_script import ActionScript
from aio_reverse.targets.action_script_loader import load_action_script
from aio_reverse.targets.web_target import WebTargetSpec


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: Path
    summary: dict[str, Any]
    turns: int
    setup_steps: int


class RunWebScriptsUseCase:
    """Opens the target once, runs setup scripts, then measured turn scripts."""

    def __init__(
        self,
        session: IWebSession,
        store: IRunStore,
        loader: Callable[[WebTargetSpec, str], ActionScript] = load_action_script,
    ) -> None:
        self._session = session
        self._store = store
        self._loader = loader

    def execute(
        self,
        turn_scripts: Sequence[str],
        *,
        setup_scripts: Sequence[str] = (),
        variables: Mapping[str, object] | None = None,
    ) -> RunResult:
        if not turn_scripts:
            raise ValueError("at least one turn script is required")
        scope = dict(variables or {})
        target = self._session.target

        setup = [self._loader(target, name) for name in setup_scripts]
        turns_plan = [
            self._loader(target, name) for name in turn_scripts
        ]

        paths = self._store.create_run(target.name)
        record: dict[str, Any] = {
            "run_id": paths.run_id,
            "target": target.name,
            "entry_url": target.entry_url,
            "port": target.chrome_port,
            "setup_scripts": list(setup_scripts),
            "turn_scripts": list(turn_scripts),
            "variables": scope,
            "started_at": _now(),
            "status": "running",
        }
        turn_summaries: list[dict[str, Any]] = []

        try:
            self._session.open()
            setup_steps = 0
            for script in setup:
                setup_turn = self._session.run_script(script, scope)
                setup_steps += len(setup_turn.steps)

            turns: list[SessionTurn] = []
            for index, script in enumerate(turns_plan, start=1):
                turn = self._session.run_script(script, scope)
                self._store.write_turn(paths, index, turn)
                turns.append(turn)
                turn_summaries.append(
                    summarise_turn(index, target, turn)
                )

            summary = summarise_run(
                paths, target, turn_summaries, setup_scripts, setup_steps
            )
            self._store.write_summary(paths, summary)

            record["turns"] = turn_summaries
            record["status"] = "completed"
            result = RunResult(
                run_id=paths.run_id,
                run_dir=paths.run_dir,
                summary=summary,
                turns=len(turns),
                setup_steps=setup_steps,
            )
        except BaseException as error:
            record["turns"] = turn_summaries
            record["status"] = "failed"
            record["error"] = f"{type(error).__name__}: {error}"
            record["finished_at"] = _now()
            try:
                self._store.write_run(paths, record)
            except BaseException as store_error:
                raise store_error from error
            raise
        else:
            record["finished_at"] = _now()
            self._store.write_run(paths, record)
            return result
        finally:
            self._session.close(keep_browser=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
