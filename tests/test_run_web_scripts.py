"""Tests for the scripted run use case and its artifact layout."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from aio_reverse.application.ports.browser_session_port import TurnCapture
from aio_reverse.application.ports.web_session_port import SessionTurn, StepRecord
from aio_reverse.application.use_cases.run_web_scripts import (
    RunWebScriptsUseCase,
)
from aio_reverse.domain.errors import (
    AuthenticationRequiredError,
    FlowTimeoutError,
)
from aio_reverse.infrastructure.artifacts import RunStore
from aio_reverse.targets.action_script import Action, ActionScript
from aio_reverse.targets.web_target import WebTargetSpec


def make_target() -> WebTargetSpec:
    return WebTargetSpec(
        name="demo",
        directory=Path("/tmp/demo-target"),
        entry_url="https://demo.test/",
        login_url="https://demo.test/login",
        login_expression="signedIn()",
        ready_expression="ready()",
        network_patterns=("/api/",),
        setup_scripts=("new_chat",),
        turn_scripts=("send_prompt",),
    )


SCRIPTS: dict[str, ActionScript] = {
    "new_chat": ActionScript(
        name="new_chat",
        actions=(Action(type="click", selector="#new-chat"),),
    ),
    "send_prompt": ActionScript(
        name="send_prompt",
        actions=(
            Action(
                type="type", selector="#input", text="{{prompt}}"
            ),
            Action(type="click", selector="#send"),
        ),
    ),
}


def load_script(target: WebTargetSpec, name: str) -> ActionScript:
    try:
        return SCRIPTS[name]
    except KeyError:
        raise ValueError(f"unknown test script {name!r}") from None


class FakeWebSession:
    def __init__(
        self,
        target: WebTargetSpec,
        *,
        fail_open: BaseException | None = None,
        fail_script: str | None = None,
    ) -> None:
        self._target = target
        self.fail_open = fail_open
        self.fail_script = fail_script
        self.calls: list[tuple[str, Any]] = []

    @property
    def target(self) -> WebTargetSpec:
        return self._target

    def open(self) -> None:
        self.calls.append(("open",))
        if self.fail_open is not None:
            raise self.fail_open

    def run_script(
        self,
        script: ActionScript,
        variables: Mapping[str, object] | None = None,
    ) -> SessionTurn:
        self.calls.append(("run_script", script.name, dict(variables or {})))
        if script.name == self.fail_script:
            raise FlowTimeoutError(f"script {script.name!r} timed out")
        return SessionTurn(
            script=script.name,
            variables=dict(variables or {}),
            steps=(
                StepRecord(
                    index=0,
                    type="click",
                    started_at=1.0,
                    ended_at=1.5,
                ),
            ),
            capture=TurnCapture(
                requests=[
                    {
                        "method": "POST",
                        "url": "https://demo.test/api/chat",
                        "status": 200,
                    },
                    {
                        "method": "GET",
                        "url": "https://demo.test/assets/app.js",
                        "status": 200,
                    },
                ],
                console=[{"type": "error", "args": ["boom"]}],
                exceptions=[{"text": "Uncaught"}],
                sse_events=[{"data": "chunk"}],
                ws_frames=[{"payload": "frame"}],
                started_at=0.5,
                ended_at=2.0,
            ),
            probe={
                "reads": [{"key": "navigator.userAgent", "count": 2}],
                "calls": [{"key": "fetch", "count": 1}],
                "events": [],
                "network": [],
                "sse": [{"url": "https://demo.test/sse"}],
                "websocket": [{"url": "wss://demo.test/ws"}],
            },
            page={"url": "https://demo.test/c/1"},
            env={"roots": []},
            started_at=1.0,
            ended_at=2.0,
        )

    def close(self, keep_browser: bool = True) -> None:
        self.calls.append(("close", keep_browser))


class RunWebScriptsUseCaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="aio-scripts-test-"))
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.run_root = self.temp / "runs"
        self.store = RunStore(self.run_root)

    def execute(
        self,
        session: FakeWebSession,
        turn_scripts: tuple[str, ...],
        setup_scripts: tuple[str, ...] = ("new_chat",),
        variables: dict[str, Any] | None = None,
    ):
        use_case = RunWebScriptsUseCase(session, self.store, loader=load_script)
        return use_case.execute(
            turn_scripts,
            setup_scripts=setup_scripts,
            variables=variables or {"prompt": "ping"},
        )

    def test_setup_scripts_run_without_turn_artifacts(self) -> None:
        session = FakeWebSession(make_target())

        result = self.execute(session, ("send_prompt", "send_prompt"))

        scripts = [
            call[1] for call in session.calls if call[0] == "run_script"
        ]
        self.assertEqual(
            scripts, ["new_chat", "send_prompt", "send_prompt"]
        )
        self.assertIn(("close", True), session.calls)
        self.assertEqual(result.turns, 2)
        self.assertEqual(result.setup_steps, 1)

        self.assertFalse((result.run_dir / "turn-00").exists())
        first = result.run_dir / "turn-01"
        second = result.run_dir / "turn-02"
        self.assertTrue(first.is_dir())
        self.assertTrue(second.is_dir())
        for name in (
            "request.json",
            "steps.json",
            "probe.json",
            "network.json",
            "sse.json",
            "websocket.json",
            "console.json",
            "exceptions.json",
            "env.json",
            "page.json",
            "timings.json",
        ):
            self.assertTrue((first / name).is_file(), name)

        record = json.loads(
            (result.run_dir / "run.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["target"], "demo")
        self.assertEqual(record["setup_scripts"], ["new_chat"])
        self.assertEqual(record["turn_scripts"], ["send_prompt", "send_prompt"])
        self.assertEqual(record["variables"], {"prompt": "ping"})
        self.assertEqual(len(record["turns"]), 2)

        summary = json.loads(
            (result.run_dir / "summary.json").read_text(encoding="utf-8")
        )
        totals = summary["totals"]
        self.assertEqual(totals["turns"], 2)
        self.assertEqual(totals["requests"], 4)
        self.assertEqual(totals["matched_requests"], 2)
        self.assertEqual(totals["sse_events"], 2)
        self.assertEqual(totals["ws_frames"], 2)
        self.assertEqual(totals["console_errors"], 2)
        self.assertEqual(totals["exceptions"], 2)
        self.assertEqual(totals["probe"]["reads"], 2)
        self.assertEqual(totals["probe"]["sse"], 2)
        self.assertEqual(totals["probe"]["websocket"], 2)
        self.assertEqual(
            summary["turns"][0]["probe"]["top_reads"],
            [{"key": "navigator.userAgent", "count": 2}],
        )

    def test_authentication_failure_writes_a_failed_run(self) -> None:
        failure = AuthenticationRequiredError(
            "not signed in; run: aio-reverse web login demo"
        )
        session = FakeWebSession(make_target(), fail_open=failure)

        with self.assertRaises(AuthenticationRequiredError):
            self.execute(session, ("send_prompt",))

        run_dirs = list((self.run_root / "demo").iterdir())
        self.assertEqual(len(run_dirs), 1)
        record = json.loads(
            (run_dirs[0] / "run.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "failed")
        self.assertIn("AuthenticationRequiredError", record["error"])
        self.assertIn("web login demo", record["error"])
        self.assertFalse((run_dirs[0] / "turn-01").exists())
        self.assertIn(("close", True), session.calls)

    def test_turn_failure_keeps_earlier_artifacts(self) -> None:
        session = FakeWebSession(
            make_target(), fail_script="send_prompt"
        )

        with self.assertRaises(FlowTimeoutError):
            self.execute(session, ("new_chat", "send_prompt"))

        run_dir = next((self.run_root / "demo").iterdir())
        self.assertTrue((run_dir / "turn-01").is_dir())
        self.assertFalse((run_dir / "turn-02").exists())
        record = json.loads(
            (run_dir / "run.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "failed")
        self.assertIn("FlowTimeoutError", record["error"])
        self.assertEqual(len(record["turns"]), 1)
        self.assertFalse((run_dir / "summary.json").exists())
        self.assertIn(("close", True), session.calls)

    def test_empty_turn_scripts_are_rejected_before_creating_a_run(self) -> None:
        session = FakeWebSession(make_target())

        with self.assertRaises(ValueError):
            self.execute(session, ())

        self.assertFalse(self.run_root.exists())
        self.assertEqual(session.calls, [])

    def test_loader_failure_prevents_a_run_directory(self) -> None:
        session = FakeWebSession(make_target())

        with self.assertRaises(ValueError):
            self.execute(session, ("missing",))

        self.assertFalse(self.run_root.exists())
        self.assertEqual(session.calls, [])


if __name__ == "__main__":
    unittest.main()
