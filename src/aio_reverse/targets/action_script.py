"""Validated action scripts that drive one browser turn."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from aio_reverse.targets.json_document import (
    optional_number,
    optional_string,
    reject_unknown_keys,
    require_integer,
)
from aio_reverse.targets.web_target import require_http_url

PRESS_KEYS = frozenset({"Enter", "Escape", "Tab", "Backspace"})

TEMPLATE_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_PLACEHOLDER_PATTERN = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)

ALLOWED_FIELDS: dict[str, frozenset[str]] = {
    "navigate": frozenset({"type", "url", "timeout_s"}),
    "click": frozenset({"type", "selector", "timeout_s"}),
    "type": frozenset({"type", "selector", "text", "timeout_s"}),
    "press": frozenset({"type", "key", "timeout_s"}),
    "wait_visible": frozenset({"type", "selector", "timeout_s"}),
    "wait_hidden": frozenset({"type", "selector", "timeout_s"}),
    "count": frozenset({"type", "selector", "save", "timeout_s"}),
    "wait_count": frozenset({"type", "selector", "greater_than", "timeout_s"}),
    "wait_network_quiet": frozenset({"type", "ms", "timeout_s"}),
    "sleep": frozenset({"type", "ms", "timeout_s"}),
    "evaluate": frozenset({"type", "expression", "save", "timeout_s"}),
}

REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "navigate": frozenset({"url"}),
    "click": frozenset({"selector"}),
    "type": frozenset({"selector", "text"}),
    "press": frozenset({"key"}),
    "wait_visible": frozenset({"selector"}),
    "wait_hidden": frozenset({"selector"}),
    "count": frozenset({"selector"}),
    "wait_count": frozenset({"selector", "greater_than"}),
    "wait_network_quiet": frozenset({"ms"}),
    "sleep": frozenset({"ms"}),
    "evaluate": frozenset({"expression"}),
}

_SAVE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Action:
    """One validated action inside a script."""

    type: str
    selector: str | None = None
    text: str | None = None
    url: str | None = None
    expression: str | None = None
    key: str | None = None
    save: str | None = None
    greater_than: int | str | None = None
    ms: int | None = None
    timeout_s: float | None = None


@dataclass(frozen=True)
class ActionScript:
    """A named sequence of actions run inside one turn."""

    name: str
    actions: tuple[Action, ...]
    timeout_s: float = 180.0
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("action script name must not be empty")
        if not self.actions:
            raise ValueError(f"action script {self.name!r} must contain at least one action")
        if self.timeout_s <= 0:
            raise ValueError(f"action script {self.name!r} timeout_s must be positive")
        self.required_variables()

    def required_variables(self) -> tuple[str, ...]:
        """External variables needed before any in-script save provides them."""
        available: set[str] = set()
        required: list[str] = []
        for index, action in enumerate(self.actions):
            context = f"action script {self.name}.actions[{index}]"
            for name in _action_template_names(action, context=context):
                if name not in available and name not in required:
                    required.append(name)
            if action.save is not None:
                available.add(action.save)
        return tuple(sorted(required))


def parse_action(index: int, document: Mapping[str, Any], *, context: str) -> Action:
    """Validate one action object and return its typed form."""
    step = f"{context}.actions[{index}]"

    action_type = document.get("type")
    if not isinstance(action_type, str) or action_type not in ALLOWED_FIELDS:
        raise ValueError(
            f"{step}: unknown action type {action_type!r}; "
            f"expected one of {sorted(ALLOWED_FIELDS)}"
        )

    reject_unknown_keys(document, ALLOWED_FIELDS[action_type], context=step)

    missing = sorted(REQUIRED_FIELDS[action_type] - set(document))
    if missing:
        raise ValueError(f"{step}: {action_type} requires keys {missing}")

    selector = optional_string(document, "selector", context=step)
    text = optional_string(document, "text", context=step)
    url = optional_string(document, "url", context=step)
    expression = optional_string(document, "expression", context=step)
    key = optional_string(document, "key", context=step)
    save = optional_string(document, "save", context=step)
    timeout_s = optional_number(document, "timeout_s", context=step)

    if timeout_s is not None and timeout_s <= 0:
        raise ValueError(f"{step}: timeout_s must be positive, got {timeout_s}")
    if url is not None:
        require_http_url(url, field_name="url", context=step)
    if key is not None and key not in PRESS_KEYS:
        raise ValueError(
            f"{step}: key must be one of {sorted(PRESS_KEYS)}, got {key!r}"
        )
    if save is not None and not _SAVE_NAME.match(save):
        raise ValueError(
            f"{step}: save must be a simple identifier, got {save!r}"
        )

    greater_than = _parse_comparison(document, step)
    ms = require_integer(document, "ms", context=step) if "ms" in document else None
    if ms is not None and ms <= 0:
        raise ValueError(f"{step}: ms must be positive, got {ms}")

    return Action(
        type=action_type,
        selector=selector,
        text=text,
        url=url,
        expression=expression,
        key=key,
        save=save,
        greater_than=greater_than,
        ms=ms,
        timeout_s=timeout_s,
    )


def _parse_comparison(document: Mapping[str, Any], step: str) -> int | str | None:
    if "greater_than" not in document:
        return None
    raw = document["greater_than"]
    if isinstance(raw, bool):
        raise ValueError(f"{step}: greater_than must be an integer, got {raw!r}")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.lstrip("-").isdigit():
            return int(text)
        names = template_names(text, context=f"{step}.greater_than")
        if len(names) == 1 and TEMPLATE_PATTERN.fullmatch(text):
            return text
    raise ValueError(
        f"{step}: greater_than must be an integer, an integer variable, "
        f"or a single template placeholder, got {raw!r}"
    )


def template_names(text: str, *, context: str) -> tuple[str, ...]:
    """Return template variable names and reject malformed placeholders."""
    for raw in _PLACEHOLDER_PATTERN.findall(text):
        placeholder = "{{" + raw + "}}"
        if not TEMPLATE_PATTERN.fullmatch(placeholder):
            raise ValueError(
                f"{context}: invalid template placeholder {placeholder!r}; "
                "expected {{name}} with an identifier"
            )
    return tuple(match.group(1) for match in TEMPLATE_PATTERN.finditer(text))


def render_templates(
    text: str,
    variables: Mapping[str, object],
    *,
    context: str,
) -> str:
    """Substitute {{name}} placeholders, failing loud on missing names."""
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            missing.append(name)
            return match.group(0)
        return str(variables[name])

    rendered = TEMPLATE_PATTERN.sub(replace, text)
    if missing:
        raise ValueError(
            f"{context}: missing template variables {sorted(set(missing))}; "
            f"provided variables: {sorted(variables)}"
        )
    return rendered


def resolve_action(
    action: Action,
    variables: Mapping[str, object],
    *,
    context: str,
) -> Action:
    """Render one action against the current variables before execution."""
    return replace(
        action,
        selector=_render_optional(action.selector, "selector", variables, context),
        text=_render_optional(action.text, "text", variables, context),
        expression=_render_optional(
            action.expression, "expression", variables, context
        ),
        greater_than=_resolve_greater_than(action.greater_than, variables, context),
    )


def _render_optional(
    value: str | None,
    field_name: str,
    variables: Mapping[str, object],
    context: str,
) -> str | None:
    if value is None:
        return None
    rendered = render_templates(value, variables, context=f"{context}.{field_name}")
    if not rendered.strip():
        raise ValueError(
            f"{context}: {field_name!r} is empty after template rendering"
        )
    return rendered


def _resolve_greater_than(
    value: int | str | None,
    variables: Mapping[str, object],
    context: str,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    rendered = render_templates(
        value, variables, context=f"{context}.greater_than"
    ).strip()
    if not rendered.lstrip("-").isdigit():
        raise ValueError(
            f"{context}: greater_than resolved to {rendered!r}, expected an integer"
        )
    return int(rendered)


def _action_template_names(action: Action, *, context: str) -> tuple[str, ...]:
    names: list[str] = []
    for field_name in ("selector", "text", "expression"):
        value = getattr(action, field_name)
        if isinstance(value, str):
            names.extend(template_names(value, context=f"{context}.{field_name}"))
    if isinstance(action.greater_than, str):
        names.extend(
            template_names(action.greater_than, context=f"{context}.greater_than")
        )
    return tuple(names)
