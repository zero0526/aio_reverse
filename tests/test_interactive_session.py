"""Tests for the interactive session that binds a target to Chrome and wre."""

from __future__ import annotations

import copy
import time
import unittest
from pathlib import Path
from typing import Any

from aio_reverse.application.interactive_session import InteractiveSession
from aio_reverse.application.ports.browser_session_port import TurnCapture
from aio_reverse.domain.errors import AuthenticationRequiredError
from aio_reverse.targets.action_script import Action, ActionScript
from aio_reverse.targets.web_target import WebTargetSpec

PROBE_SOURCE = "(function () { var root = { drain: function () { return {}; } }; })();"
PROBE_SNAPSHOT = {
    "reads": [],
    "calls": [],
    "events": [],
    "network": [],
    "sse": [],
    "websocket": [],
}


def make_target() -> WebTargetSpec:
    return WebTargetSpec(
        name="demo",
        directory=Path("/tmp/demo-target"),
        entry_url="https://demo.test/",
        login_url="https://demo.test/login",
        login_expression="signedIn()",
        ready_expression="ready()",
        network_patterns=("/api/",),
        body_capture_patterns=("/api/",),
        chrome_port=9555,
    )


class FakeToolkit:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def start_browser(
        self,
        port: int,
        headless: bool = False,
        profile: Path | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("start_browser", port, headless, profile))
        return {"running": True, "port": port}

    def stop_browser(self, port: int) -> dict[str, Any]:
        self.calls.append(("stop_browser", port))
        return {"running": False}

    def emit_probe(self, probe: Any, name: str = "__WRE") -> str:
        self.calls.append(("emit_probe", probe, name))
        return PROBE_SOURCE

    def env_script(self, depth: int) -> str:
        self.calls.append(("env_script", depth))
        return "ENV_SCRIPT"


class FakeBrowser:
    def __init__(
        self,
        url: str = "https://demo.test/",
        logged_in: bool = True,
        probe_snapshot: dict[str, Any] | None = None,
    ) -> None:
        self.url = url
        self.logged_in = logged_in
        self.probe_present = False
        self.probe_snapshot = probe_snapshot or PROBE_SNAPSHOT
        self.calls: list[tuple[str, Any]] = []

    def attach(self, port: int, url_prefix: str | None = None) -> None:
        self.calls.append(("attach", port, url_prefix))

    def list_pages(self) -> list[dict[str, Any]]:
        return []

    def navigate(self, url: str, timeout_s: float = 60.0) -> None:
        self.calls.append(("navigate", url))
        self.url = url

    def reload(self, timeout_s: float = 60.0) -> None:
        self.calls.append(("reload",))

    def evaluate(self, expression: str, timeout_s: float = 30.0) -> Any:
        self.calls.append(("evaluate", expression))
        if expression == PROBE_SOURCE:
            self.probe_present = True
            return None
        if "typeof window.__WRE" in expression:
            return self.probe_present
        if expression == "ready()":
            return True
        if expression == "signedIn()":
            return self.logged_in
        return None

    def insert_text(self, text: str) -> None:
        self.calls.append(("insert_text", text))

    def click(self, selector: str, timeout_s: float = 30.0) -> None:
        self.calls.append(("click", selector))

    def press(self, key: str) -> None:
        self.calls.append(("press", key))

    def add_init_script(self, source: str) -> None:
        self.calls.append(("add_init_script", source))

    def begin_turn(self) -> None:
        self.calls.append(("begin_turn",))

    def end_turn(self) -> TurnCapture:
        self.calls.append(("end_turn",))
        return TurnCapture(started_at=1.0, ended_at=2.0)

    def drain_probe(self) -> dict[str, Any]:
        self.calls.append(("drain_probe",))
        return copy.deepcopy(self.probe_snapshot)

    def snapshot_env(self, script: str) -> dict[str, Any]:
        self.calls.append(("snapshot_env", script))
        return {"roots": []}

    def page_info(self) -> dict[str, Any]:
        self.calls.append(("page_info",))
        return {"url": self.url}

    def outer_html(self) -> str:
        self.calls.append(("outer_html",))
        return "<html><body>demo</body></html>"

    def last_network_activity(self) -> float:
        return time.monotonic()

    def close(self) -> None:
        self.calls.append(("close",))


class InteractiveSessionTest(unittest.TestCase):
    def make_session(
        self,
        browser: FakeBrowser | None = None,
    ) -> tuple[InteractiveSession, FakeToolkit, FakeBrowser]:
        toolkit = FakeToolkit()
        page = browser or FakeBrowser()
        session = InteractiveSession(
            make_target(),
            toolkit,
            page,
            Path("/tmp/profile-demo"),
        )
        return session, toolkit, page

    def test_open_uses_persistent_profile_and_injects_probe(self) -> None:
        session, toolkit, browser = self.make_session()

        session.open()

        start = toolkit.calls[0]
        self.assertEqual(start[0], "start_browser")
        self.assertEqual(start[1], 9555)
        self.assertEqual(start[3], Path("/tmp/profile-demo"))
        self.assertIn(("attach", 9555, "https://demo.test"), browser.calls)
        self.assertIn(
            ("emit_probe", make_target().probe, "__WRE"), toolkit.calls
        )
        self.assertIn(("add_init_script", PROBE_SOURCE), browser.calls)
        self.assertIn(("evaluate", PROBE_SOURCE), browser.calls)
        self.assertTrue(browser.probe_present)

    def test_open_navigates_when_the_page_is_off_origin(self) -> None:
        session, _, browser = self.make_session(FakeBrowser("about:blank"))

        session.open()

        self.assertIn(("navigate", "https://demo.test/"), browser.calls)

    def test_open_without_login_raises_with_command(self) -> None:
        session, toolkit, browser = self.make_session(
            FakeBrowser(logged_in=False)
        )

        with self.assertRaises(AuthenticationRequiredError) as caught:
            session.open()

        self.assertIn("web login demo", str(caught.exception))
        self.assertNotIn("emit_probe", [call[0] for call in toolkit.calls])
        self.assertFalse(browser.probe_present)

    def test_inject_probe_skips_an_existing_probe(self) -> None:
        session, toolkit, browser = self.make_session()
        browser.probe_present = True

        session.inject_probe()

        self.assertNotIn("emit_probe", [call[0] for call in toolkit.calls])

    def test_run_script_orders_probe_drain_around_the_actions(self) -> None:
        session, _, browser = self.make_session()
        session.open()
        script = ActionScript(
            name="turn",
            actions=(Action(type="click", selector="#send"),),
        )

        turn = session.run_script(script, {"prompt": "ping"})

        names = [call[0] for call in browser.calls]
        start = names.index("begin_turn")
        order = names[start:]
        self.assertLess(order.index("click"), order.index("drain_probe"))
        self.assertLess(order.index("drain_probe"), order.index("page_info"))
        self.assertLess(order.index("page_info"), order.index("snapshot_env"))
        self.assertLess(order.index("snapshot_env"), order.index("end_turn"))
        self.assertEqual(turn.script, "turn")
        self.assertEqual(turn.variables, {"prompt": "ping"})
        self.assertEqual(len(turn.steps), 1)
        self.assertEqual(turn.probe, PROBE_SNAPSHOT)
        self.assertEqual(turn.page, {"url": "https://demo.test/"})
        self.assertEqual(turn.env, {"roots": []})

    def test_run_script_applies_the_probe_body_policy(self) -> None:
        browser = FakeBrowser(
            probe_snapshot={
                **PROBE_SNAPSHOT,
                "network": [
                    {"url": "https://demo.test/api/action", "body": "keep"},
                    {"url": "https://demo.test/telemetry", "body": "drop"},
                ],
            }
        )
        session, _, _ = self.make_session(browser)
        session.open()
        script = ActionScript(
            name="turn",
            actions=(Action(type="click", selector="#send"),),
        )

        turn = session.run_script(script)

        kept, dropped = turn.probe["network"]
        self.assertEqual(kept["body"], "keep")
        self.assertNotIn("body_redacted", kept)
        self.assertIsNone(dropped["body"])
        self.assertTrue(dropped["body_redacted"])

    def test_navigate_requires_http_and_reinjects(self) -> None:
        session, _, browser = self.make_session()
        session.open()

        with self.assertRaises(ValueError):
            session.navigate("file:///etc/passwd")

        session.navigate("https://demo.test/chat")
        self.assertIn(("navigate", "https://demo.test/chat"), browser.calls)

    def test_dump_state_returns_page_and_env(self) -> None:
        session, _, _ = self.make_session()

        state = session.dump_state()

        self.assertEqual(state["page"]["url"], "https://demo.test/")
        self.assertEqual(state["env"], {"roots": []})

    def test_capture_page_pairs_url_and_outer_html(self) -> None:
        session, _, browser = self.make_session()

        snapshot = session.capture_page("home")

        self.assertEqual(snapshot.label, "home")
        self.assertEqual(snapshot.url, "https://demo.test/")
        self.assertEqual(snapshot.html, "<html><body>demo</body></html>")
        self.assertIsNotNone(snapshot.captured_at.tzinfo)
        names = [call[0] for call in browser.calls]
        self.assertLess(names.index("page_info"), names.index("outer_html"))

    def test_close_keeps_or_stops_chrome(self) -> None:
        session, toolkit, browser = self.make_session()
        session.open()

        session.close()
        self.assertIn(("close",), browser.calls)
        self.assertNotIn("stop_browser", [call[0] for call in toolkit.calls])

        session.close(keep_browser=False)
        self.assertIn(("stop_browser", 9555), toolkit.calls)


if __name__ == "__main__":
    unittest.main()
