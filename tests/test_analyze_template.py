"""Tests for the differential template analysis use case."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aio_reverse.application.use_cases.analyze_template import (
    AnalyzeTemplateUseCase,
)


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
            "reduction_ratio": 0.5,
            "skeleton": "[document]\n  [p] \"x\"",
            "slots": [{"path": "p[1]", "tag": "p", "role": "content"}],
        }


class AnalyzeTemplateUseCaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="aio-template-test-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.a = self.root / "a.html"
        self.b = self.root / "b.html"
        self.a.write_text("<html></html>", encoding="utf-8")
        self.b.write_text("<html></html>", encoding="utf-8")
        self.toolkit = FakeToolkit()
        self.use_case = AnalyzeTemplateUseCase(self.toolkit)

    def test_execute_passes_pages_and_maps_result(self) -> None:
        result = self.use_case.execute([self.a, self.b], xpath=True)

        self.assertEqual(self.toolkit.calls, [([self.a, self.b], True)])
        self.assertEqual(result.pages, 2)
        self.assertEqual(result.reduction_ratio, 0.5)
        self.assertIn("[document]", result.skeleton)
        self.assertEqual(result.slots[0]["tag"], "p")

    def test_execute_requires_two_pages(self) -> None:
        with self.assertRaises(ValueError):
            self.use_case.execute([self.a])

    def test_execute_requires_html_suffix(self) -> None:
        txt = self.root / "c.txt"
        txt.write_text("x", encoding="utf-8")

        with self.assertRaises(ValueError) as caught:
            self.use_case.execute([self.a, txt])
        self.assertIn("c.txt", str(caught.exception))

    def test_execute_requires_existing_files(self) -> None:
        missing = self.root / "gone.html"

        with self.assertRaises(ValueError) as caught:
            self.use_case.execute([self.a, missing])
        self.assertIn(str(missing), str(caught.exception))

    def test_execute_does_not_call_toolkit_on_invalid_input(self) -> None:
        with self.assertRaises(ValueError):
            self.use_case.execute([self.a])

        self.assertEqual(self.toolkit.calls, [])


if __name__ == "__main__":
    unittest.main()
