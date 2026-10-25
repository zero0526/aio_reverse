"""Tests for the capture page snapshot use case."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from aio_reverse.application.page_snapshot import PageSnapshot
from aio_reverse.application.use_cases.capture_page_snapshot import (
    CapturePageSnapshotUseCase,
)
from aio_reverse.infrastructure.artifacts.html_snapshot_store import HtmlSnapshotStore

HTML = "<html><body>hi</body></html>"


class FakeSession:
    def __init__(self) -> None:
        self.target = SimpleNamespace(name="demo")
        self.closed: bool | None = None

    def capture_page(self, label: str) -> PageSnapshot:
        return PageSnapshot(
            label=label,
            url="https://demo.test/",
            html=HTML,
            captured_at=datetime.now(timezone.utc),
        )

    def close(self, keep_browser: bool = True) -> None:
        self.closed = keep_browser


class ExplodingStore:
    def write(self, target_name: str, label: str, html: str):
        raise RuntimeError("store failed")


class CapturePageSnapshotUseCaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="aio-capture-test-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.session = FakeSession()
        self.store = HtmlSnapshotStore(self.root)

    def test_execute_writes_file_and_leaves_session_open(self) -> None:
        use_case = CapturePageSnapshotUseCase(self.session, self.store)

        captured = use_case.execute("  home  ")

        self.assertEqual(captured.url, "https://demo.test/")
        self.assertEqual(captured.snapshot.label, "home")
        self.assertTrue(captured.snapshot.path.is_file())
        self.assertEqual(
            captured.snapshot.path.read_text(encoding="utf-8"), HTML
        )
        self.assertEqual(captured.snapshot.bytes, len(HTML.encode("utf-8")))
        self.assertIsNone(self.session.closed)

    def test_blank_label_is_rejected_before_touching_the_session(self) -> None:
        use_case = CapturePageSnapshotUseCase(self.session, self.store)

        for label in ("", "   ", None):
            with self.assertRaises(ValueError):
                use_case.execute(label)
        self.assertIsNone(self.session.closed)

    def test_store_failure_propagates_loudly(self) -> None:
        use_case = CapturePageSnapshotUseCase(self.session, ExplodingStore())

        with self.assertRaises(RuntimeError):
            use_case.execute("home")


if __name__ == "__main__":
    unittest.main()
