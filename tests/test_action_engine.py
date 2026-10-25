"""Tests for the action-script execution engine."""

from __future__ import annotations

import json
import time
import unittest
from typing import Any

from aio_reverse.application.action_engine import ActionEngine
from aio_reverse.domain.errors import ActionScriptError, BrowserSessionError
from aio_reverse.targets.action_script import Action, ActionScript


class FakeBrowserSession:
    """Minimal page session that records calls and answers waiter probes."""

    def __init__(self, count: int = 0) -> None:
        self.count = count
        self.calls: list[tuple[str, Any]] = []
        self.timeouts: list[tuple[str, str, float]] = []
        self.node_missing = False
        self.query_calls = 0

    def navigate(self, url: str, timeout_s: float = 60.0) -> None:
        self.calls.append(("navigate", url))

    def click(self, selector: str, timeout_s: float = 30.0) -> None:
        self.calls.append(("click", selector))
        self.timeouts.append(("click", selector, timeout_s))
        if self.node_missing:
            raise BrowserSessionError(f"no node matches {selector!r}")

    def insert_text(self, text: str) -> None:
        self.calls.append(("insert_text", text))

    def press(self, key: str) -> None:
        self.calls.append(("press", key))

    def evaluate(self, expression: str, timeout_s: float = 30.0) -> Any:
        self.calls.append(("evaluate", expression))
        if "document.querySelectorAll(" not in expression:
            if expression == "42":
                return 42
            return None
        selector = json.loads(
            expression.split("document.querySelectorAll(", 1)[1].split(")", 1)[0]
        )
        if expression.endswith(" === 0"):
            return selector == "#d"
        if expression.endswith(" > 0"):
            return selector == "#c"
        self.query_calls += 1
        return self.count if self.query_calls == 1 else self.count + 1

    def last_network_activity(self) -> float:
        return time.monotonic() - 60.0


class ActionEngineTest(unittest.TestCase):
    def test_saved_count_is_available_to_later_steps(self) -> None:
        browser = FakeBrowserSession(count=3)
        actions = (
            Action(type="count", selector="#reply", save="replies_before"),
            Action(
                type="wait_count",
                selector="#reply",
                greater_than="{{replies_before}}",
                timeout_s=2,
            ),
            Action(type="type", selector="#input", text="{{prompt}}"),
        )

        records = ActionEngine(browser).run(
            ActionScript(name="test", actions=actions),
            {"prompt": "ping"},
        )

        self.assertEqual(len(records), 3)
        self.assertEqual(records[0].saved, "replies_before")
        self.assertEqual(records[0].value, 3)
        self.assertIn(("click", "#input"), browser.calls)
        self.assertIn(("insert_text", "ping"), browser.calls)

    def test_missing_external_variable_fails_before_any_action(self) -> None:
        browser = FakeBrowserSession()
        script = ActionScript(
            name="test",
            actions=(
                Action(type="type", selector="#input", text="{{prompt}}"),
            ),
        )

        with self.assertRaises(ValueError) as caught:
            ActionEngine(browser).run(script)

        self.assertIn("['prompt']", str(caught.exception))
        self.assertEqual(browser.calls, [])

    def test_failure_is_wrapped_with_step_context(self) -> None:
        browser = FakeBrowserSession()
        browser.node_missing = True
        script = ActionScript(
            name="test",
            actions=(Action(type="click", selector="#send"),),
        )

        with self.assertRaises(ActionScriptError) as caught:
            ActionEngine(browser).run(script)

        error = caught.exception
        self.assertEqual(error.script, "test")
        self.assertEqual(error.step_index, 0)
        self.assertEqual(error.action_type, "click")
        self.assertIn("no node matches '#send'", error.message)
        self.assertIsInstance(error.__cause__, BrowserSessionError)

    def test_save_without_a_value_is_loud(self) -> None:
        script = ActionScript(
            name="test",
            actions=(
                Action(type="evaluate", expression="undefined", save="value"),
            ),
        )

        with self.assertRaises(ActionScriptError) as caught:
            ActionEngine(FakeBrowserSession()).run(script)

        self.assertIn("produced no value", caught.exception.message)

    def test_each_action_type_reaches_the_session(self) -> None:
        browser = FakeBrowserSession(count=2)
        script = ActionScript(
            name="test",
            actions=(
                Action(type="navigate", url="https://example.test/"),
                Action(type="click", selector="#a"),
                Action(type="type", selector="#b", text="hello"),
                Action(type="press", key="Enter"),
                Action(type="wait_visible", selector="#c", timeout_s=1),
                Action(type="wait_hidden", selector="#d", timeout_s=1),
                Action(type="count", selector="#e", save="n"),
                Action(
                    type="wait_count",
                    selector="#f",
                    greater_than=1,
                    timeout_s=1,
                ),
                Action(type="wait_network_quiet", ms=10, timeout_s=1),
                Action(type="sleep", ms=1),
                Action(type="evaluate", expression="42", save="value"),
            ),
        )

        records = ActionEngine(browser).run(script)

        self.assertEqual(len(records), 11)
        self.assertEqual(records[6].value, 2)
        self.assertEqual(records[10].value, 42)
        self.assertIn(("navigate", "https://example.test/"), browser.calls)
        self.assertIn(("press", "Enter"), browser.calls)

    def test_script_timeout_fails_before_a_slow_step(self) -> None:
        browser = FakeBrowserSession()
        script = ActionScript(
            name="slow",
            actions=(
                Action(type="sleep", ms=200),
                Action(type="click", selector="#send"),
            ),
            timeout_s=0.05,
        )

        with self.assertRaises(ActionScriptError) as caught:
            ActionEngine(browser).run(script)

        error = caught.exception
        self.assertEqual(error.script, "slow")
        self.assertEqual(error.step_index, 0)
        self.assertIn("timeout", error.message)
        self.assertEqual(browser.calls, [])

    def test_script_deadline_caps_the_action_timeout(self) -> None:
        browser = FakeBrowserSession()
        script = ActionScript(
            name="capped",
            actions=(Action(type="click", selector="#send", timeout_s=999),),
            timeout_s=0.2,
        )

        ActionEngine(browser).run(script)

        method, selector, timeout_s = browser.timeouts[0]
        self.assertEqual((method, selector), ("click", "#send"))
        self.assertGreater(timeout_s, 0)
        self.assertLessEqual(timeout_s, 0.2)


if __name__ == "__main__":
    unittest.main()
