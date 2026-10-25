"""Tests for JavaScript expressions that filter to rendered elements."""

from __future__ import annotations

import unittest

from aio_reverse.application.page_element_expressions import (
    first_visible_click_point_expression,
    visible_absence_expression,
    visible_count_expression,
    visible_presence_expression,
)


class PageElementExpressionTest(unittest.TestCase):
    def test_count_only_keeps_rendered_matches(self) -> None:
        expression = visible_count_expression('div[data-mode="compact"]')

        self.assertIn(
            'document.querySelectorAll("div[data-mode=\\"compact\\"]")',
            expression,
        )
        self.assertIn("getBoundingClientRect", expression)
        self.assertIn("getComputedStyle", expression)
        self.assertTrue(expression.endswith(".length"))

    def test_presence_and_absence_wrap_the_rendered_count(self) -> None:
        present = visible_presence_expression("#send")
        absent = visible_absence_expression("#send")

        self.assertEqual(present, f"{visible_count_expression('#send')} > 0")
        self.assertEqual(
            absent, f"{visible_count_expression('#send')} === 0"
        )

    def test_click_uses_the_first_rendered_match(self) -> None:
        expression = first_visible_click_point_expression(
            'button[aria-label="Send"]'
        )

        self.assertIn("document.querySelectorAll", expression)
        self.assertIn(".filter(", expression)
        self.assertIn("[0]", expression)
        self.assertIn("scrollIntoView", expression)
        self.assertIn("matches.length", expression)
        self.assertIn("click target not found or not rendered", expression)


if __name__ == "__main__":
    unittest.main()
