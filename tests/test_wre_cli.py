"""Unit tests for the wre CLI adapter."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aio_reverse.adapters.toolkit.wre_cli import WreToolkit, resolve_binary
from aio_reverse.domain.errors import ToolkitError, ToolkitNotFoundError
from aio_reverse.targets.web_target import TargetProbeConfig

FIXTURE = Path(__file__).parent / "fixtures" / "fake_wre.py"


class WreToolkitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="aio-wre-test-"))
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.binary = self.temp / "fake_wre"
        shutil.copy(FIXTURE, self.binary)
        self.binary.chmod(self.binary.stat().st_mode | stat.S_IXUSR)
        self.workspace = self.temp / "workspace"
        self.argv_file = self.temp / "argv.json"
        self.env_patch = mock.patch.dict(
            os.environ, {"FAKE_WRE_ARGV": str(self.argv_file)}, clear=False
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.toolkit = WreToolkit(self.workspace, binary=self.binary)

    def recorded(self) -> list[str]:
        return json.loads(self.argv_file.read_text(encoding="utf-8"))

    def test_version(self) -> None:
        self.assertEqual(self.toolkit.version(), "wre 9.9.9")

    def test_start_browser_always_requests_status(self) -> None:
        result = self.toolkit.start_browser(9445, headless=True)

        self.assertTrue(result["running"])
        argv = self.recorded()
        self.assertIn("browser", argv)
        self.assertIn("--start", argv)
        self.assertIn("--status", argv)
        self.assertIn("--headless", argv)
        self.assertEqual(argv[argv.index("--port") + 1], "9445")

    def test_start_browser_forwards_profile(self) -> None:
        profile = self.temp / "profiles" / "chatgpt"

        self.toolkit.start_browser(9445, profile=profile)

        argv = self.recorded()
        self.assertEqual(argv[argv.index("--profile") + 1], str(profile))

    def test_emit_probe_builds_flags_and_returns_source(self) -> None:
        probe = TargetProbeConfig(
            preset="minimal",
            properties=("navigator.userAgent",),
            methods=("canvas.toDataURL",),
            events=("fetch",),
            network=False,
            workers=True,
            stealth=False,
            call_sites=False,
            sse=False,
            websocket=False,
        )

        source = self.toolkit.emit_probe(probe, name="__TEST")

        self.assertIn("drain", source)
        argv = self.recorded()
        self.assertIn("probe", argv)
        self.assertIn("emit", argv)
        self.assertEqual(argv[argv.index("--name") + 1], "__TEST")
        self.assertEqual(argv[argv.index("--preset") + 1], "minimal")
        for flag, value in (
            ("--property", "navigator.userAgent"),
            ("--method", "canvas.toDataURL"),
            ("--event", "fetch"),
        ):
            self.assertEqual(argv[argv.index(flag) + 1], value)
        for flag in (
            "--no-network",
            "--workers",
            "--no-stealth",
            "--no-call-sites",
            "--no-sse",
            "--no-websocket",
        ):
            self.assertIn(flag, argv)

    def test_capture_arguments_and_result(self) -> None:
        out = self.temp / "capture"
        result = self.toolkit.capture("https://example.test/", out, 9333)

        self.assertEqual(result["id"], "cap-1")
        argv = self.recorded()
        self.assertIn("--root", argv)
        self.assertIn(str(self.workspace.resolve()), argv)
        self.assertIn("--json", argv)
        self.assertIn("capture", argv)
        self.assertIn("--keep-storage", argv)
        self.assertIn("--scripts", argv)
        self.assertIn("--out", argv)
        self.assertIn(str(out), argv)

    def test_capture_forwards_profile(self) -> None:
        profile = self.temp / "profiles" / "chatgpt"

        self.toolkit.capture(
            "https://example.test/", self.temp / "capture", 9333, profile=profile
        )

        argv = self.recorded()
        self.assertEqual(argv[argv.index("--profile") + 1], str(profile))

    def test_template_diff_builds_argv_and_returns_object(self) -> None:
        pages = [self.temp / "home.html", self.temp / "thread.html"]

        result = self.toolkit.template_diff(pages, xpath=True)

        argv = self.recorded()
        start = argv.index("template")
        self.assertEqual(argv[start : start + 3], ["template", "diff", "--xpath"])
        self.assertEqual(argv[start + 3 :], [str(page) for page in pages])
        self.assertIn("--json", argv)
        self.assertEqual(result["pages"], 2)
        self.assertEqual(result["first_page"], "home.html")
        self.assertIn("[dynamic]", result["skeleton"])
        self.assertEqual(result["slots"][0]["tag"], "p")

    def test_template_diff_without_xpath_omits_the_flag(self) -> None:
        pages = [self.temp / "home.html", self.temp / "thread.html"]

        self.toolkit.template_diff(pages)

        argv = self.recorded()
        self.assertNotIn("--xpath", argv)

    def test_template_diff_requires_two_pages(self) -> None:
        with self.assertRaises(ValueError):
            self.toolkit.template_diff([self.temp / "only.html"])

    def test_template_diff_rejects_invalid_json(self) -> None:
        with mock.patch.dict(os.environ, {"FAKE_WRE_BAD_JSON": "1"}):
            with self.assertRaises(ToolkitError) as caught:
                self.toolkit.template_diff(
                    [self.temp / "a.html", self.temp / "b.html"]
                )

        self.assertIn("invalid JSON", str(caught.exception))

    def test_template_diff_rejects_malformed_object(self) -> None:
        with mock.patch.dict(os.environ, {"FAKE_WRE_BAD_TEMPLATE": "1"}):
            with self.assertRaises(ToolkitError) as caught:
                self.toolkit.template_diff(
                    [self.temp / "a.html", self.temp / "b.html"]
                )

        self.assertIn("expected at least 2", str(caught.exception))

    def test_env_script_omits_json_flag(self) -> None:
        source = self.toolkit.env_script(4)

        self.assertIn("navigator", source)
        argv = self.recorded()
        self.assertNotIn("--json", argv)
        self.assertEqual(argv[-4:], ["env", "script", "--depth", "4"])

    def test_failure_is_loud(self) -> None:
        with mock.patch.dict(os.environ, {"FAKE_WRE_FAIL": "1"}):
            with self.assertRaises(ToolkitError) as caught:
                self.toolkit.start_browser(9333)

        self.assertEqual(caught.exception.returncode, 3)
        self.assertIn("fake wre failure", caught.exception.stderr or "")

    def test_invalid_json_is_loud(self) -> None:
        with mock.patch.dict(os.environ, {"FAKE_WRE_BAD_JSON": "1"}):
            with self.assertRaises(ToolkitError) as caught:
                self.toolkit.markers()

        self.assertIn("invalid JSON", str(caught.exception))

    def test_markers(self) -> None:
        markers = self.toolkit.markers()
        self.assertEqual(markers[0]["name"], "webdriver-true")
        self.assertTrue(markers[0]["source"])

    def test_pools_requires_design_fields(self) -> None:
        design = self.toolkit.pools()
        self.assertEqual(design["markers"], ["webdriver-true"])

    def test_sweep_requires_baselines_and_arms(self) -> None:
        with self.assertRaises(ValueError):
            self.toolkit.sweep([self.temp / "one.json"], [("a", self.temp / "a.json")])
        with self.assertRaises(ValueError):
            self.toolkit.sweep([self.temp / "a", self.temp / "b"], [])

    def test_missing_explicit_binary(self) -> None:
        with self.assertRaises(ToolkitNotFoundError):
            WreToolkit(self.workspace, binary=self.temp / "nope")

    def test_resolve_binary_from_env(self) -> None:
        with mock.patch.dict(os.environ, {"WRE_BIN": str(self.binary)}):
            self.assertEqual(resolve_binary(), self.binary)

    def test_bundle_file(self) -> None:
        self.assertEqual(
            self.toolkit.bundle_file(self.temp / "cap"),
            self.temp / "cap" / "bundle.json",
        )


if __name__ == "__main__":
    unittest.main()
