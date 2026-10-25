"""Runtime.evaluate expressions that only consider rendered page elements."""

from __future__ import annotations

import json

_VISIBLE_FILTER = (
    ".filter(function (element) {"
    " const rect = element.getBoundingClientRect();"
    " const style = getComputedStyle(element);"
    " return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden';"
    "})"
)


def visible_count_expression(selector: str) -> str:
    """JavaScript expression returning how many matches are rendered."""
    literal = json.dumps(selector)
    return (
        f"Array.from(document.querySelectorAll({literal}))"
        f"{_VISIBLE_FILTER}.length"
    )


def visible_presence_expression(selector: str) -> str:
    """JavaScript expression that is true when at least one match is rendered."""
    return f"{visible_count_expression(selector)} > 0"


def visible_absence_expression(selector: str) -> str:
    """JavaScript expression that is true when no match is rendered."""
    return f"{visible_count_expression(selector)} === 0"


def first_visible_click_point_expression(selector: str) -> str:
    """JavaScript expression returning the centre of the first rendered match."""
    literal = json.dumps(selector)
    return (
        "(() => {"
        f" const matches = Array.from(document.querySelectorAll({literal}));"
        f" const element = matches{_VISIBLE_FILTER}[0];"
        " if (!element) throw new Error("
        f"'click target not found or not rendered: ' + {literal} + "
        "' (matches: ' + matches.length + ')');"
        " element.scrollIntoView({block: 'center', inline: 'center'});"
        " const rect = element.getBoundingClientRect();"
        " return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};"
        "})()"
    )
