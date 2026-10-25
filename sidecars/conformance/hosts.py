"""Shared fixtures and host lookup for the sidecar conformance suite."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from aio_sidecar import (
    BadInput,
    Blocked,
    Cancelled,
    ErrorKind,
    InternalError,
    ProtocolError,
    ResourceError,
    TargetDrift,
    Timeout,
    Unsupported,
)

ROOT = Path(__file__).resolve().parents[2]
ECHO_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "echo.descriptor.json"
ECHO_DESCRIPTOR = json.loads(ECHO_FIXTURE.read_text(encoding="utf-8"))

SKIP_MISSING_ENV = "SIDECAR_CONFORMANCE_SKIP_MISSING"

ERROR_KIND_CLASSES = {
    ErrorKind.BAD_INPUT: BadInput,
    ErrorKind.UNSUPPORTED: Unsupported,
    ErrorKind.TARGET_DRIFT: TargetDrift,
    ErrorKind.BLOCKED: Blocked,
    ErrorKind.TIMEOUT: Timeout,
    ErrorKind.CANCELLED: Cancelled,
    ErrorKind.RESOURCE: ResourceError,
    ErrorKind.PROTOCOL: ProtocolError,
    ErrorKind.INTERNAL: InternalError,
}


@dataclass(frozen=True)
class EchoHost:
    name: str
    binary: str
    build: str


def discover_hosts() -> tuple[list[EchoHost], list[EchoHost]]:
    candidates = [
        EchoHost(
            name="node",
            binary=os.environ.get("SIDECAR_ECHO_NODE")
            or str(ROOT / "sidecars" / "node" / "examples" / "echo"),
            build="chmod +x sidecars/node/examples/echo (node must be on PATH)",
        ),
        EchoHost(
            name="cpp",
            binary=os.environ.get("SIDECAR_ECHO_CPP")
            or str(ROOT / "sidecars" / "cpp" / "build" / "echo_engine"),
            build=(
                "cmake -S sidecars/cpp -B sidecars/cpp/build "
                "-DCMAKE_BUILD_TYPE=Release && "
                "cmake --build sidecars/cpp/build -j"
            ),
        ),
        EchoHost(
            name="rust",
            binary=os.environ.get("SIDECAR_ECHO_RUST")
            or str(ROOT / "sidecars" / "rust" / "target" / "debug" / "examples" / "echo"),
            build="cargo build --manifest-path sidecars/rust/Cargo.toml --example echo",
        ),
    ]

    available: list[EchoHost] = []
    missing: list[EchoHost] = []
    for host in candidates:
        path = Path(host.binary)
        if path.is_file() and os.access(path, os.X_OK):
            available.append(host)
        else:
            missing.append(host)
    return available, missing


def require_hosts() -> list[EchoHost]:
    """Returns the available engines; fails loud when a build is missing."""
    available, missing = discover_hosts()
    if missing and os.environ.get(SKIP_MISSING_ENV) != "1":
        details = "\n".join(
            f"- {host.name}: missing executable {host.binary}\n  build: {host.build}"
            for host in missing
        )
        raise AssertionError(
            "sidecar conformance engines are missing:\n"
            f"{details}\n"
            f"set {SKIP_MISSING_ENV}=1 to skip unavailable hosts"
        )
    return available
