"""Loads and validates action scripts for a web target."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aio_reverse.targets.action_script import Action, ActionScript, parse_action
from aio_reverse.targets.json_document import (
    load_json_object,
    optional_number,
    optional_string,
    reject_unknown_keys,
    require_string,
)
from aio_reverse.targets.web_target import WebTargetSpec

SCRIPT_KEYS = frozenset({"name", "description", "timeout_s", "actions"})


def load_action_script(target: WebTargetSpec, script_name: str) -> ActionScript:
    """Read and validate one script from targets/<name>/scripts/.

    Templates stay unresolved: save values are only known while the script runs.
    Call `ActionScript.required_variables()` to check external variables.
    """
    path = target.script_path(script_name)
    context = f"action script {target.name}/{script_name} ({path})"
    document = load_json_object(path, context=context)
    reject_unknown_keys(document, SCRIPT_KEYS, context=context)

    name = require_string(document, "name", context=context)
    if name != script_name:
        raise ValueError(
            f"{context}: name {name!r} does not match file stem {script_name!r}"
        )

    raw_actions = document.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise ValueError(f"{context}: actions must be a non-empty list")

    actions: list[Action] = []
    for index, item in enumerate(raw_actions):
        if not isinstance(item, Mapping):
            raise ValueError(f"{context}.actions[{index}] must be a JSON object")
        actions.append(parse_action(index, item, context=context))

    timeout_s = optional_number(document, "timeout_s", context=context, default=180.0)
    description = optional_string(document, "description", context=context) or ""

    return ActionScript(
        name=name,
        actions=tuple(actions),
        timeout_s=timeout_s,
        description=description,
    )
