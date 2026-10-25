"""Tests for MCP tool wiring and the long-lived session registry."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from unittest import mock

from mcp.server.mcpserver import MCPServer

from aio_reverse.adapters.mcp import build_server
from aio_reverse.adapters.mcp.session_registry import SessionRegistry
from aio_reverse.adapters.mcp.web_tools import (
    WebToolServices,
    register_web_tools,
)
from aio_reverse.application.page_snapshot import PageSnapshot
from aio_reverse.application.ports.browser_session_port import TurnCapture
from aio_reverse.application.ports.web_session_port import (
    SessionTurn,
    SnapshotFile,
    StepRecord,
)
from aio_reverse.domain.errors import BrowserSessionError
from aio_reverse.infrastructure.artifacts import RunStore
from aio_reverse.targets.action_script import Action, ActionScript
from aio_reverse.targets.web_target import WebTargetSpec

TOOL_NAMES = {
    "web_targets",
    "web_open",
    "web_run_script",
    "web_state",
    "web_snapshot",
    "web_skeleton",
    "web_inject_probe",
    "web_click",
    "web_type",
    "web_press",
    "web_evaluate",
    "web_navigate",
    "web_close",
}


def make_target(name: str = "demo") -> WebTargetSpec:
    return WebTargetSpec(
        name=name,
        directory=Path(f"/tmp/{name}-target"),
        entry_url=f"https://{name}.test/",
        login_url=f"https://{name}.test/login",
        login_expression="signedIn()",
        ready_expression="ready()",
        network_patterns=("/api/",),
        setup_scripts=("new_chat",),
        turn_scripts=("send_prompt",),
    )


class FakeTargetRegistry:
    def __init__(self, targets: list[WebTargetSpec]) -> None:
        self._targets = {target.name: target for target in targets}

    def names(self) -> list[str]:
        return sorted(self._targets)

    def resolve(self, name: str) -> WebTargetSpec:
        try:
            return self._targets[name]
        except KeyError:
            raise ValueError(f"unknown web target {name!r}") from None


class FakeSession:
    def __init__(self, target: WebTargetSpec) -> None:
        self._target = target
        self.calls: list[tuple[str, Any]] = []
        self.url = target.entry_url

    @property
    def target(self) -> WebTargetSpec:
        return self._target

    def open(self) -> None:
        self.calls.append(("open",))

    def login(self, timeout_s: float = 300.0) -> dict[str, Any]:
        return self.dump_state()["page"]

    def run_script(
        self,
        script: ActionScript,
        variables: Mapping[str, object] | None = None,
    ) -> SessionTurn:
        self.calls.append(("run_script", script.name))
        return SessionTurn(
            script=script.name,
            variables=dict(variables or {}),
            steps=(
                StepRecord(
                    index=0, type="click", started_at=0.0, ended_at=0.5
                ),
            ),
            capture=TurnCapture(
                requests=[
                    {
                        "method": "POST",
                        "url": f"{self._target.entry_url}api/chat",
                        "status": 200,
                    }
                ],
                sse_events=[{"data": "chunk"}],
                ws_frames=[{"payload": "frame"}],
                started_at=0.0,
                ended_at=1.0,
            ),
            probe={
                "reads": [],
                "calls": [],
                "events": [],
                "network": [],
                "sse": [],
                "websocket": [],
            },
            page={"url": self.url},
            env={"roots": []},
            started_at=0.0,
            ended_at=1.0,
        )

    def click(self, selector: str) -> None:
        self.calls.append(("click", selector))

    def type_text(self, text: str) -> None:
        self.calls.append(("type_text", text))

    def press(self, key: str) -> None:
        self.calls.append(("press", key))

    def evaluate(self, expression: str) -> Any:
        self.calls.append(("evaluate", expression))
        return {"expression": expression}

    def navigate(self, url: str) -> None:
        self.calls.append(("navigate", url))
        self.url = url

    def inject_probe(self) -> None:
        self.calls.append(("inject_probe",))

    def dump_state(self) -> dict[str, Any]:
        self.calls.append(("dump_state",))
        return {"page": {"url": self.url}, "env": {"roots": []}}

    def capture_page(self, label: str) -> PageSnapshot:
        self.calls.append(("capture_page", label))
        return PageSnapshot(
            label=label,
            url=self.url,
            html="<html><body>live</body></html>",
            captured_at=datetime.now(timezone.utc),
        )

    def close(self, keep_browser: bool = True) -> None:
        self.calls.append(("close", keep_browser))


class FakeToolkit:
    def __init__(self) -> None:
        self.calls: list[tuple[list[Path], bool]] = []

    def template_diff(
        self, pages: list[Path], *, xpath: bool = False
    ) -> dict[str, Any]:
        self.calls.append((list(pages), xpath))
        return {
            "pages": len(pages),
            "first_page": pages[0].name,
            "reduction_ratio": 0.25,
            "skeleton": "[document]\n  [p] \"x\"",
            "slots": [{"path": "p[1]", "tag": "p", "role": "content"}],
        }


class FakeSnapshotStore:
    def __init__(self) -> None:
        self.writes: list[tuple[str, str, str]] = []

    def write(self, target_name: str, label: str, html: str) -> SnapshotFile:
        self.writes.append((target_name, label, html))
        return SnapshotFile(
            label=label,
            path=Path("/tmp") / f"{target_name}-{label}.html",
            bytes=len(html.encode("utf-8")),
            sha256="sha",
        )


def load_script(target: WebTargetSpec, name: str) -> ActionScript:
    return ActionScript(
        name=name,
        actions=(Action(type="click", selector="#send"),),
    )


class SessionRegistryTest(unittest.TestCase):
    def registry(
        self, targets: list[WebTargetSpec]
    ) -> tuple[SessionRegistry, list[FakeSession]]:
        created: list[FakeSession] = []

        def factory(target: WebTargetSpec) -> FakeSession:
            session = FakeSession(target)
            created.append(session)
            return session

        return SessionRegistry(FakeTargetRegistry(targets), factory), created

    def test_acquire_creates_one_session_per_target(self) -> None:
        registry, created = self.registry([make_target("demo")])

        first = registry.acquire("demo")
        second = registry.acquire("demo")

        self.assertIs(first, second)
        self.assertEqual(len(created), 1)

    def test_unknown_target_is_loud(self) -> None:
        registry, _ = self.registry([make_target("demo")])

        with self.assertRaises(ValueError):
            registry.acquire("missing")

    def test_close_reports_whether_a_session_was_open(self) -> None:
        registry, _ = self.registry([make_target("demo")])

        self.assertFalse(registry.close("demo"))
        registry.acquire("demo")
        self.assertTrue(registry.close("demo"))
        self.assertFalse(registry.close("demo"))

    def test_close_all_attempts_every_session_and_reports_failure(self) -> None:
        registry, _ = self.registry([make_target("one"), make_target("two")])
        first = registry.acquire("one")
        second = registry.acquire("two")
        first.close = mock.Mock(side_effect=RuntimeError("close failed"))

        with self.assertRaises(BrowserSessionError) as caught:
            registry.close_all()

        self.assertIn("1 of 2", str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__, RuntimeError)
        first.close.assert_called_once_with(keep_browser=True)
        self.assertIn(("close", True), second.calls)


class WebToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="aio-mcp-test-"))
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.target = make_target()
        self.targets = FakeTargetRegistry([self.target])
        self.created: list[FakeSession] = []
        self.sessions = SessionRegistry(
            self.targets, self.factory
        )
        self.store = RunStore(self.temp / "runs")
        self.toolkit = FakeToolkit()
        self.snapshots = FakeSnapshotStore()
        self.services = WebToolServices(
            self.targets,
            self.store,
            self.sessions,
            self.toolkit,
            self.snapshots,
            loader=load_script,
        )
        self.server = MCPServer("test")
        register_web_tools(self.server, self.services)

    def factory(self, target: WebTargetSpec) -> FakeSession:
        session = FakeSession(target)
        self.created.append(session)
        return session

    def call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = asyncio.run(self.server.call_tool(name, arguments or {}))
        self.assertFalse(getattr(result, "is_error", False))
        return json.loads(result.content[0].text)

    def test_registers_thirteen_web_tools(self) -> None:
        tools = asyncio.run(self.server.list_tools())

        self.assertEqual({tool.name for tool in tools}, TOOL_NAMES)

    def test_build_server_exposes_tools_without_touching_chrome(self) -> None:
        built = build_server(toolkit=mock.Mock())

        tools = asyncio.run(built.server.list_tools())
        self.assertEqual({tool.name for tool in tools}, TOOL_NAMES)

    def test_web_targets_returns_target_metadata(self) -> None:
        result = self.call("web_targets")

        self.assertEqual(
            result["targets"],
            [
                {
                    "name": "demo",
                    "entry_url": "https://demo.test/",
                    "login_url": "https://demo.test/login",
                    "chrome_port": 9333,
                    "setup_scripts": ["new_chat"],
                    "turn_scripts": ["send_prompt"],
                    "probe_preset": "fingerprint",
                    "body_capture_patterns": [],
                    "stream_payloads": False,
                }
            ],
        )

    def test_web_open_and_state_reuse_one_session(self) -> None:
        opened = self.call("web_open", {"target": "demo"})
        state = self.call("web_state", {"target": "demo"})

        self.assertEqual(opened["page"]["url"], "https://demo.test/")
        self.assertEqual(state["env"], {"roots": []})
        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.created[0].calls.count(("open",)), 1)

    def test_web_run_script_returns_run_and_totals(self) -> None:
        result = self.call(
            "web_run_script",
            {
                "target": "demo",
                "script": "send_prompt",
                "variables": {"prompt": "ping"},
            },
        )

        self.assertTrue(Path(result["run_dir"]).is_dir())
        self.assertEqual(result["turn"]["script"], "send_prompt")
        self.assertEqual(result["turn"]["variables"], {"prompt": "ping"})
        self.assertEqual(result["turn"]["requests"], 1)
        self.assertEqual(result["totals"]["matched_requests"], 1)
        self.assertIn("probe", result["totals"])
        self.assertIn(("close", True), self.created[0].calls)

    def test_handover_tools_drive_the_session(self) -> None:
        self.assertEqual(
            self.call("web_click", {"target": "demo", "selector": "#send"}),
            {"target": "demo", "clicked": "#send"},
        )
        self.assertEqual(
            self.call("web_type", {"target": "demo", "text": "hello"}),
            {"target": "demo", "typed_characters": 5},
        )
        self.assertEqual(
            self.call("web_press", {"target": "demo", "key": "Enter"}),
            {"target": "demo", "pressed": "Enter"},
        )
        self.assertEqual(
            self.call(
                "web_evaluate",
                {"target": "demo", "expression": "document.title"},
            ),
            {"target": "demo", "result": {"expression": "document.title"}},
        )
        page = self.call(
            "web_navigate",
            {"target": "demo", "url": "https://demo.test/chat"},
        )
        self.assertEqual(page["page"]["url"], "https://demo.test/chat")
        self.assertEqual(
            self.call("web_inject_probe", {"target": "demo"}),
            {"target": "demo", "probe": "__WRE"},
        )

        session = self.created[0]
        self.assertIn(("click", "#send"), session.calls)
        self.assertIn(("type_text", "hello"), session.calls)
        self.assertIn(("press", "Enter"), session.calls)
        self.assertIn(("navigate", "https://demo.test/chat"), session.calls)
        self.assertIn(("inject_probe",), session.calls)

    def test_web_snapshot_writes_and_returns_metadata(self) -> None:
        result = self.call("web_snapshot", {"target": "demo", "label": "home"})

        self.assertEqual(
            result,
            {
                "target": "demo",
                "label": "home",
                "url": "https://demo.test/",
                "path": "/tmp/demo-home.html",
                "bytes": len("<html><body>live</body></html>"),
                "sha256": "sha",
            },
        )
        self.assertEqual(
            self.snapshots.writes,
            [("demo", "home", "<html><body>live</body></html>")],
        )
        session = self.created[0]
        self.assertIn(("capture_page", "home"), session.calls)
        self.assertNotIn(("close", True), session.calls)

    def test_web_skeleton_differs_two_pages(self) -> None:
        a = self.temp / "a.html"
        b = self.temp / "b.html"
        a.write_text("<html></html>", encoding="utf-8")
        b.write_text("<html></html>", encoding="utf-8")

        result = self.call(
            "web_skeleton",
            {"pages": [str(a), str(b)], "xpath": True},
        )

        self.assertEqual(self.toolkit.calls, [([a, b], True)])
        self.assertEqual(result["pages"], 2)
        self.assertEqual(result["reduction_ratio"], 0.25)
        self.assertIn("[document]", result["skeleton"])
        self.assertEqual(result["slots"][0]["tag"], "p")

    def test_web_close_keeps_or_stops_chrome(self) -> None:
        self.call("web_open", {"target": "demo"})

        kept = self.call("web_close", {"target": "demo"})
        self.assertTrue(kept["closed"])
        self.assertEqual(kept["browser"], "kept running")
        self.assertIn(("close", True), self.created[0].calls)

        self.call("web_open", {"target": "demo"})
        stopped = self.call(
            "web_close", {"target": "demo", "keep_browser": False}
        )
        self.assertEqual(stopped["browser"], "stopped")
        self.assertIn(("close", False), self.created[-1].calls)


if __name__ == "__main__":
    unittest.main()
