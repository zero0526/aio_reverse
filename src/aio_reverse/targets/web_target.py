"""Declarative configuration for one web target and its Rust probe."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

PROBE_PRESETS = ("fingerprint", "minimal", "none")


def require_http_url(value: str, *, field_name: str, context: str) -> str:
    """Return the URL when it is absolute http(s), otherwise fail loud."""
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"{context}: {field_name} must be an http(s) URL, got {value!r}")
    return value


def _validate_trap(value: str, *, field_name: str, context: str) -> None:
    holder, _, name = value.rpartition(".")
    if not holder or not name:
        raise ValueError(
            f"{context}: {field_name} entries must look like holder.name, got {value!r}"
        )


@dataclass(frozen=True)
class TargetProbeConfig:
    """The Rust probe surface installed for a target."""

    preset: str = "fingerprint"
    properties: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    network: bool = True
    workers: bool = True
    stealth: bool = True
    call_sites: bool = True
    sse: bool = True
    websocket: bool = True

    def __post_init__(self) -> None:
        if self.preset not in PROBE_PRESETS:
            raise ValueError(
                f"probe.preset must be one of {PROBE_PRESETS}, got {self.preset!r}"
            )
        for value in self.properties:
            _validate_trap(value, field_name="probe.properties", context="target")
        for value in self.methods:
            _validate_trap(value, field_name="probe.methods", context="target")
        for value in self.events:
            if not value.strip():
                raise ValueError("probe.events must not contain empty strings")


@dataclass(frozen=True)
class WebTargetSpec:
    """Everything Python needs to drive one web target."""

    name: str
    directory: Path
    entry_url: str
    login_url: str
    login_expression: str
    ready_expression: str
    network_patterns: tuple[str, ...] = ()
    body_capture_patterns: tuple[str, ...] = ()
    stream_payloads: bool = False
    env_depth: int = 4
    chrome_port: int = 9333
    setup_scripts: tuple[str, ...] = ()
    turn_scripts: tuple[str, ...] = ()
    probe: TargetProbeConfig = field(default_factory=TargetProbeConfig)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("target.name must not be empty")
        if not isinstance(self.directory, Path):
            raise ValueError(f"target.directory must be a Path, got {self.directory!r}")
        require_http_url(self.entry_url, field_name="entry_url", context="target")
        require_http_url(self.login_url, field_name="login_url", context="target")
        if not self.login_expression.strip():
            raise ValueError("target.login_expression must not be empty")
        if not self.ready_expression.strip():
            raise ValueError("target.ready_expression must not be empty")
        if self.env_depth < 1:
            raise ValueError("target.env_depth must be at least 1")
        if not 1 <= self.chrome_port <= 65535:
            raise ValueError("target.chrome_port must be a valid TCP port")
        for field_name, patterns in (
            ("network_patterns", self.network_patterns),
            ("body_capture_patterns", self.body_capture_patterns),
        ):
            for pattern in patterns:
                if not pattern:
                    raise ValueError(
                        f"target.{field_name} must not contain empty strings"
                    )
        if not isinstance(self.stream_payloads, bool):
            raise ValueError(
                "target.stream_payloads must be a boolean, got "
                f"{self.stream_payloads!r}"
            )
        for group, names in (
            ("setup_scripts", self.setup_scripts),
            ("turn_scripts", self.turn_scripts),
        ):
            for name in names:
                if not name.strip():
                    raise ValueError(f"target.{group} must not contain empty strings")
        if not isinstance(self.probe, TargetProbeConfig):
            raise ValueError(
                f"target.probe must be TargetProbeConfig, got {type(self.probe).__name__}"
            )

    @property
    def origin(self) -> str:
        parts = urlsplit(self.entry_url)
        return f"{parts.scheme}://{parts.netloc}"

    def script_path(self, script_name: str) -> Path:
        """Return the JSON script path, without checking that it exists."""
        if not script_name.strip():
            raise ValueError("script name must not be empty")
        return self.directory / "scripts" / f"{script_name}.json"
