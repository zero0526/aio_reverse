"""Loads a web target from targets/<name>/target.json."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aio_reverse.targets.json_document import (
    load_json_object,
    optional_boolean,
    optional_integer,
    optional_string_list,
    reject_unknown_keys,
    require_string,
)
from aio_reverse.targets.web_target import TargetProbeConfig, WebTargetSpec

TARGET_KEYS = frozenset(
    {
        "name",
        "entry_url",
        "login_url",
        "login_expression",
        "ready_expression",
        "network_patterns",
        "body_capture_patterns",
        "stream_payloads",
        "env_depth",
        "chrome_port",
        "setup_scripts",
        "turn_scripts",
        "probe",
    }
)

PROBE_KEYS = frozenset(
    {
        "preset",
        "properties",
        "methods",
        "events",
        "network",
        "workers",
        "stealth",
        "call_sites",
        "sse",
        "websocket",
    }
)


def load_target(directory: Path) -> WebTargetSpec:
    """Read and validate one target directory."""
    directory = directory.resolve()
    path = directory / "target.json"
    context = f"target manifest {path}"
    document = load_json_object(path, context=context)
    reject_unknown_keys(document, TARGET_KEYS, context=context)

    name = require_string(document, "name", context=context)
    if name != directory.name:
        raise ValueError(
            f"{context}: name {name!r} does not match directory {directory.name!r}"
        )

    setup_scripts = optional_string_list(document, "setup_scripts", context=context)
    turn_scripts = optional_string_list(document, "turn_scripts", context=context)

    spec = WebTargetSpec(
        name=name,
        directory=directory,
        entry_url=require_string(document, "entry_url", context=context),
        login_url=require_string(document, "login_url", context=context),
        login_expression=require_string(document, "login_expression", context=context),
        ready_expression=require_string(document, "ready_expression", context=context),
        network_patterns=optional_string_list(
            document, "network_patterns", context=context
        ),
        body_capture_patterns=optional_string_list(
            document, "body_capture_patterns", context=context
        ),
        stream_payloads=optional_boolean(
            document, "stream_payloads", context=context, default=False
        ),
        env_depth=optional_integer(document, "env_depth", context=context, default=4),
        chrome_port=optional_integer(
            document, "chrome_port", context=context, default=9333
        ),
        setup_scripts=setup_scripts,
        turn_scripts=turn_scripts,
        probe=_parse_probe(document.get("probe"), context=context),
    )

    for script_name in (*setup_scripts, *turn_scripts):
        script_path = spec.script_path(script_name)
        if not script_path.is_file():
            raise FileNotFoundError(
                f"{context}: script {script_name!r} is listed but {script_path} does not exist"
            )

    return spec


def _parse_probe(value: Any, *, context: str) -> TargetProbeConfig:
    if value is None:
        return TargetProbeConfig()
    if not isinstance(value, Mapping):
        raise ValueError(f"{context}: probe must be a JSON object")

    reject_unknown_keys(value, PROBE_KEYS, context=f"{context}.probe")

    preset = value.get("preset", "fingerprint")
    if not isinstance(preset, str):
        raise ValueError(
            f"{context}.probe: preset must be a string, got {preset!r}"
        )

    return TargetProbeConfig(
        preset=preset,
        properties=optional_string_list(
            value, "properties", context=f"{context}.probe"
        ),
        methods=optional_string_list(value, "methods", context=f"{context}.probe"),
        events=optional_string_list(value, "events", context=f"{context}.probe"),
        network=optional_boolean(
            value, "network", context=f"{context}.probe", default=True
        ),
        workers=optional_boolean(
            value, "workers", context=f"{context}.probe", default=True
        ),
        stealth=optional_boolean(
            value, "stealth", context=f"{context}.probe", default=True
        ),
        call_sites=optional_boolean(
            value, "call_sites", context=f"{context}.probe", default=True
        ),
        sse=optional_boolean(value, "sse", context=f"{context}.probe", default=True),
        websocket=optional_boolean(
            value, "websocket", context=f"{context}.probe", default=True
        ),
    )
