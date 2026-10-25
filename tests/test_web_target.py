"""Tests for loading target.json and resolving targets from disk."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aio_reverse.targets.target_loader import load_target
from aio_reverse.targets.target_registry import TargetRegistry
from aio_reverse.targets.web_target import TargetProbeConfig, WebTargetSpec

BASE_TARGET: dict[str, Any] = {
    "name": "example",
    "entry_url": "https://example.test/app",
    "login_url": "https://example.test/login",
    "login_expression": "login()",
    "ready_expression": "ready()",
    "setup_scripts": ["setup"],
    "turn_scripts": ["turn"],
}


class TargetLoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "example"
        scripts = self.directory / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "setup.json").write_text(
            json.dumps({"name": "setup", "actions": [{"type": "click", "selector": "#new"}]}),
            encoding="utf-8",
        )
        (scripts / "turn.json").write_text(
            json.dumps(
                {
                    "name": "turn",
                    "actions": [{"type": "click", "selector": "#send"}],
                }
            ),
            encoding="utf-8",
        )
        self.write_target(BASE_TARGET)

    def write_target(self, document: dict[str, Any]) -> None:
        (self.directory / "target.json").write_text(
            json.dumps(document), encoding="utf-8"
        )

    def test_loads_a_valid_target(self) -> None:
        spec = load_target(self.directory)

        self.assertIsInstance(spec, WebTargetSpec)
        self.assertEqual(spec.name, "example")
        self.assertEqual(spec.origin, "https://example.test")
        self.assertEqual(spec.entry_url, "https://example.test/app")
        self.assertEqual(spec.setup_scripts, ("setup",))
        self.assertEqual(spec.turn_scripts, ("turn",))
        self.assertEqual(spec.probe.preset, "fingerprint")
        self.assertEqual(spec.env_depth, 4)
        self.assertEqual(spec.chrome_port, 9333)
        self.assertTrue(spec.script_path("turn").is_file())

    def test_defaults_do_not_capture_bodies_or_stream_payloads(self) -> None:
        spec = load_target(self.directory)

        self.assertEqual(spec.body_capture_patterns, ())
        self.assertFalse(spec.stream_payloads)

    def test_loads_body_capture_and_stream_policy(self) -> None:
        self.write_target(
            dict(
                BASE_TARGET,
                body_capture_patterns=["/backend-api/"],
                stream_payloads=True,
            )
        )

        spec = load_target(self.directory)

        self.assertEqual(spec.body_capture_patterns, ("/backend-api/",))
        self.assertTrue(spec.stream_payloads)

    def test_rejects_empty_body_capture_pattern(self) -> None:
        self.write_target(dict(BASE_TARGET, body_capture_patterns=[" "]))

        with self.assertRaises(ValueError) as caught:
            load_target(self.directory)
        self.assertIn("body_capture_patterns", str(caught.exception))

    def test_rejects_non_boolean_stream_payloads(self) -> None:
        self.write_target(dict(BASE_TARGET, stream_payloads="yes"))

        with self.assertRaises(ValueError) as caught:
            load_target(self.directory)
        self.assertIn("stream_payloads", str(caught.exception))

    def test_rejects_unknown_keys(self) -> None:
        self.write_target(dict(BASE_TARGET, extra=True))

        with self.assertRaises(ValueError) as caught:
            load_target(self.directory)
        self.assertIn("unknown keys", str(caught.exception))

    def test_rejects_non_http_entry_url(self) -> None:
        self.write_target(dict(BASE_TARGET, entry_url="file:///tmp/app.html"))

        with self.assertRaises(ValueError) as caught:
            load_target(self.directory)
        self.assertIn("http(s)", str(caught.exception))

    def test_rejects_name_directory_mismatch(self) -> None:
        self.write_target(dict(BASE_TARGET, name="other"))

        with self.assertRaises(ValueError) as caught:
            load_target(self.directory)
        self.assertIn("does not match directory", str(caught.exception))

    def test_rejects_missing_listed_script(self) -> None:
        self.write_target(dict(BASE_TARGET, turn_scripts=["missing"]))

        with self.assertRaises(FileNotFoundError) as caught:
            load_target(self.directory)
        self.assertIn("missing.json", str(caught.exception))

    def test_rejects_bad_probe_preset(self) -> None:
        self.write_target(dict(BASE_TARGET, probe={"preset": "nope"}))

        with self.assertRaises(ValueError) as caught:
            load_target(self.directory)
        self.assertIn("probe.preset", str(caught.exception))

    def test_rejects_bad_probe_trap(self) -> None:
        self.write_target(dict(BASE_TARGET, probe={"properties": ["nodot"]}))

        with self.assertRaises(ValueError) as caught:
            load_target(self.directory)
        self.assertIn("holder.name", str(caught.exception))

    def test_probe_defaults_enable_streams_and_stealth(self) -> None:
        probe = TargetProbeConfig()

        self.assertTrue(probe.network)
        self.assertTrue(probe.workers)
        self.assertTrue(probe.stealth)
        self.assertTrue(probe.call_sites)
        self.assertTrue(probe.sse)
        self.assertTrue(probe.websocket)


class TargetRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "example"
        (self.directory / "scripts").mkdir(parents=True)
        (self.directory / "target.json").write_text(
            json.dumps(dict(BASE_TARGET, setup_scripts=[], turn_scripts=[])),
            encoding="utf-8",
        )

    def test_lists_and_resolves_targets(self) -> None:
        registry = TargetRegistry(self.root)

        self.assertEqual(registry.names(), ["example"])
        self.assertEqual(registry.resolve("example").name, "example")

    def test_unknown_target_lists_known_names(self) -> None:
        registry = TargetRegistry(self.root)

        with self.assertRaises(ValueError) as caught:
            registry.resolve("missing")
        self.assertIn("example", str(caught.exception))

    def test_rejects_path_traversal(self) -> None:
        registry = TargetRegistry(self.root)

        with self.assertRaises(ValueError):
            registry.resolve("../example")


if __name__ == "__main__":
    unittest.main()
