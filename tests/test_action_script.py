"""Tests for action script validation, templating and loading."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aio_reverse.targets.action_script import (
    ActionScript,
    parse_action,
    resolve_action,
)
from aio_reverse.targets.action_script_loader import load_action_script
from aio_reverse.targets.target_loader import load_target
from aio_reverse.targets.web_target import WebTargetSpec

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_target(directory: Path) -> WebTargetSpec:
    return WebTargetSpec(
        name="example",
        directory=directory,
        entry_url="https://example.test/app",
        login_url="https://example.test/login",
        login_expression="login()",
        ready_expression="ready()",
    )


class ActionScriptLoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        (self.directory / "scripts").mkdir()
        self.target = make_target(self.directory)

    def write_script(self, name: str, document: dict[str, Any]) -> None:
        path = self.directory / "scripts" / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")

    @staticmethod
    def script(actions: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
        document: dict[str, Any] = {"name": "turn", "actions": actions}
        document.update(overrides)
        return document

    def test_preserves_templates_and_reports_required_variables(self) -> None:
        self.write_script(
            "turn",
            self.script(
                [{"type": "type", "selector": "#input", "text": "{{prompt}}"}]
            ),
        )

        script = load_action_script(self.target, "turn")

        self.assertIsInstance(script, ActionScript)
        self.assertEqual(script.actions[0].text, "{{prompt}}")
        self.assertEqual(script.required_variables(), ("prompt",))

    def test_required_variables_skip_values_saved_earlier(self) -> None:
        self.write_script(
            "turn",
            self.script(
                [
                    {"type": "count", "selector": "#reply", "save": "before"},
                    {
                        "type": "wait_count",
                        "selector": "#reply",
                        "greater_than": "{{before}}",
                    },
                ]
            ),
        )

        self.assertEqual(load_action_script(self.target, "turn").required_variables(), ())

    def test_required_variables_still_require_later_variables(self) -> None:
        self.write_script(
            "turn",
            self.script(
                [
                    {"type": "count", "selector": "#reply", "save": "before"},
                    {"type": "type", "selector": "#input", "text": "{{prompt}}"},
                ]
            ),
        )

        self.assertEqual(
            load_action_script(self.target, "turn").required_variables(), ("prompt",)
        )

    def test_rejects_invalid_template_placeholder(self) -> None:
        self.write_script(
            "turn",
            self.script(
                [{"type": "type", "selector": "#input", "text": "{{9bad}}"}]
            ),
        )

        with self.assertRaises(ValueError) as caught:
            load_action_script(self.target, "turn")
        self.assertIn("invalid template placeholder", str(caught.exception))

    def test_rejects_unknown_script_keys(self) -> None:
        self.write_script(
            "turn",
            self.script([{"type": "sleep", "ms": 10}], extra=True),
        )

        with self.assertRaises(ValueError) as caught:
            load_action_script(self.target, "turn")
        self.assertIn("unknown keys", str(caught.exception))

    def test_rejects_name_file_mismatch(self) -> None:
        self.write_script(
            "turn",
            {"name": "other", "actions": [{"type": "sleep", "ms": 10}]},
        )

        with self.assertRaises(ValueError) as caught:
            load_action_script(self.target, "turn")
        self.assertIn("does not match", str(caught.exception))

    def test_rejects_empty_actions(self) -> None:
        self.write_script("turn", self.script([]))

        with self.assertRaises(ValueError) as caught:
            load_action_script(self.target, "turn")
        self.assertIn("non-empty list", str(caught.exception))

    def test_missing_script_file_fails_loud(self) -> None:
        with self.assertRaises(FileNotFoundError) as caught:
            load_action_script(self.target, "missing")
        self.assertIn("missing.json", str(caught.exception))

    def test_applies_script_timeout_and_description(self) -> None:
        self.write_script(
            "turn",
            self.script(
                [{"type": "sleep", "ms": 10}],
                timeout_s=12.5,
                description="demo turn",
            ),
        )

        script = load_action_script(self.target, "turn")

        self.assertEqual(script.timeout_s, 12.5)
        self.assertEqual(script.description, "demo turn")

    def test_default_script_timeout(self) -> None:
        self.write_script("turn", self.script([{"type": "sleep", "ms": 10}]))

        self.assertEqual(load_action_script(self.target, "turn").timeout_s, 180.0)

    def test_loads_the_shipped_chatgpt_target(self) -> None:
        target = load_target(PROJECT_ROOT / "targets" / "chatgpt")

        script = load_action_script(target, "send_prompt")

        self.assertEqual(script.name, "send_prompt")
        self.assertEqual(script.required_variables(), ("prompt",))


class TemplateResolutionTest(unittest.TestCase):
    def parse(self, document: dict[str, Any], index: int = 0):
        return parse_action(index, document, context="script")

    def test_renders_text_and_integer_variable(self) -> None:
        action = self.parse(
            {
                "type": "wait_count",
                "selector": "#reply",
                "greater_than": "{{before}}",
            }
        )

        resolved = resolve_action(action, {"before": 2}, context="script.actions[0]")

        self.assertEqual(resolved.greater_than, 2)

    def test_missing_variable_lists_its_name(self) -> None:
        action = self.parse(
            {"type": "type", "selector": "#input", "text": "hello {{user}}"}
        )

        with self.assertRaises(ValueError) as caught:
            resolve_action(action, {}, context="script.actions[0]")
        self.assertIn("user", str(caught.exception))

    def test_rejects_empty_rendered_text(self) -> None:
        action = self.parse(
            {"type": "type", "selector": "#input", "text": "{{empty}}"}
        )

        with self.assertRaises(ValueError) as caught:
            resolve_action(action, {"empty": ""}, context="script.actions[0]")
        self.assertIn("empty after template rendering", str(caught.exception))

    def test_rejects_non_numeric_greater_than_variable(self) -> None:
        action = self.parse(
            {
                "type": "wait_count",
                "selector": "#reply",
                "greater_than": "{{before}}",
            }
        )

        with self.assertRaises(ValueError) as caught:
            resolve_action(action, {"before": "many"}, context="script.actions[0]")
        self.assertIn("expected an integer", str(caught.exception))


class ActionValidationTest(unittest.TestCase):
    def parse(self, document: dict[str, Any], index: int = 0):
        return parse_action(index, document, context="script")

    def test_rejects_unknown_action_type(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.parse({"type": "drag", "selector": "#x"})
        self.assertIn("unknown action type", str(caught.exception))

    def test_rejects_unknown_action_field(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.parse({"type": "click", "selector": "#x", "text": "oops"})
        self.assertIn("unknown keys", str(caught.exception))

    def test_rejects_missing_required_field(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.parse({"type": "click"})
        self.assertIn("requires keys", str(caught.exception))

    def test_rejects_unsupported_press_key(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.parse({"type": "press", "key": "F5"})
        self.assertIn("key must be one of", str(caught.exception))

    def test_accepts_whitelisted_press_key(self) -> None:
        self.assertEqual(self.parse({"type": "press", "key": "Enter"}).key, "Enter")

    def test_rejects_non_http_navigate_url(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.parse({"type": "navigate", "url": "file:///tmp/x.html"})
        self.assertIn("http(s)", str(caught.exception))

    def test_rejects_templated_navigate_url(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.parse({"type": "navigate", "url": "{{url}}"})
        self.assertIn("http(s)", str(caught.exception))

    def test_rejects_non_positive_ms(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.parse({"type": "sleep", "ms": 0})
        self.assertIn("ms must be positive", str(caught.exception))

    def test_rejects_non_positive_action_timeout(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.parse({"type": "click", "selector": "#x", "timeout_s": 0})
        self.assertIn("timeout_s must be positive", str(caught.exception))

    def test_rejects_bad_save_identifier(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.parse({"type": "count", "selector": "#x", "save": "not valid"})
        self.assertIn("identifier", str(caught.exception))

    def test_rejects_boolean_greater_than(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.parse(
                {"type": "wait_count", "selector": "#x", "greater_than": True}
            )
        self.assertIn("greater_than", str(caught.exception))

    def test_rejects_non_numeric_greater_than(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.parse(
                {"type": "wait_count", "selector": "#x", "greater_than": "many"}
            )
        self.assertIn("greater_than", str(caught.exception))

    def test_accepts_integer_string_greater_than(self) -> None:
        self.assertEqual(
            self.parse(
                {"type": "wait_count", "selector": "#x", "greater_than": "3"}
            ).greater_than,
            3,
        )

    def test_evaluate_accepts_save(self) -> None:
        action = self.parse(
            {"type": "evaluate", "expression": "1 + 1", "save": "result"}
        )

        self.assertEqual(action.save, "result")


if __name__ == "__main__":
    unittest.main()
