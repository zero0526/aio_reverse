"""Tests for shared artifact naming and the HTML snapshot store."""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aio_reverse.infrastructure.artifacts.artifact_naming import safe_name, utc_stamp
from aio_reverse.infrastructure.artifacts.html_snapshot_store import HtmlSnapshotStore

HTML = "<html><body><p>Snapshot nội dung</p></body></html>"


class ArtifactNamingTest(unittest.TestCase):
    def test_safe_name_sanitizes_and_falls_back(self) -> None:
        self.assertEqual(safe_name("fake chat!"), "fake-chat")
        self.assertEqual(safe_name("../x"), "..-x")
        self.assertEqual(safe_name("///"), "target")

    def test_utc_stamp_shape(self) -> None:
        self.assertRegex(utc_stamp(), r"^\d{8}T\d{6}Z$")


class HtmlSnapshotStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="aio-snap-test-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.store = HtmlSnapshotStore(self.root)

    def test_write_stores_file_and_metadata(self) -> None:
        with mock.patch(
            "aio_reverse.infrastructure.artifacts.html_snapshot_store.utc_stamp",
            return_value="20261025T000000Z",
        ):
            snapshot = self.store.write("demo target", "home page", HTML)

        expected = self.root / "demo-target" / "snapshots" / "20261025T000000Z-home-page.html"
        self.assertEqual(snapshot.path, expected)
        self.assertEqual(snapshot.label, "home-page")
        self.assertEqual(expected.read_text(encoding="utf-8"), HTML)
        self.assertEqual(snapshot.bytes, len(HTML.encode("utf-8")))
        self.assertEqual(snapshot.sha256, hashlib.sha256(HTML.encode("utf-8")).hexdigest())

    def test_write_refuses_to_overwrite(self) -> None:
        with mock.patch(
            "aio_reverse.infrastructure.artifacts.html_snapshot_store.utc_stamp",
            return_value="20261025T000000Z",
        ):
            self.store.write("demo", "home", HTML)
            with self.assertRaises(FileExistsError):
                self.store.write("demo", "home", HTML)

    def test_write_rejects_empty_html(self) -> None:
        with self.assertRaises(ValueError):
            self.store.write("demo", "home", "   ")

    def test_config_snapshots_dir_matches_store_layout(self) -> None:
        from aio_reverse.infrastructure.config import AppConfig

        config = AppConfig(base_data_dir=self.root)
        store = HtmlSnapshotStore(config.web_output_dir)

        snapshot = store.write("demo", "home", HTML)

        self.assertEqual(snapshot.path.parent, config.html_snapshots_dir("demo"))


if __name__ == "__main__":
    unittest.main()
