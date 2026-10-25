"""Port for crate-backed toolkit operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Sequence

from aio_reverse.targets.web_target import TargetProbeConfig


class IToolkitPort(ABC):
    """Operations delegated to the Rust ``wre`` CLI."""

    @abstractmethod
    def version(self) -> str:
        """Return the toolkit version string."""

    @abstractmethod
    def start_browser(
        self,
        port: int,
        headless: bool = False,
        profile: Path | None = None,
    ) -> dict[str, Any]:
        """Launch or attach the shared Chrome instance."""

    @abstractmethod
    def stop_browser(self, port: int) -> dict[str, Any]:
        """Shut down the shared Chrome instance."""

    @abstractmethod
    def emit_probe(
        self,
        probe: TargetProbeConfig,
        name: str = "__WRE",
    ) -> str:
        """Return the JavaScript source of the Rust probe."""

    @abstractmethod
    def capture(
        self,
        url: str,
        out_dir: Path,
        port: int,
        *,
        wait_s: int = 20,
        keep_storage: bool = True,
        scripts: bool = True,
        profile: Path | None = None,
    ) -> dict[str, Any]:
        """Run a one-shot capture and install the crate probe on the page target."""

    @abstractmethod
    def template_diff(
        self,
        pages: Sequence[Path],
        *,
        xpath: bool = False,
    ) -> dict[str, Any]:
        """Run differential template analysis over at least two HTML pages."""

    @abstractmethod
    def env_script(self, depth: int) -> str:
        """Return the JavaScript that snapshots the page environment."""

    @abstractmethod
    def markers(self) -> list[dict[str, Any]]:
        """Return the built-in automation markers."""

    @abstractmethod
    def pools(self, one_at_a_time: bool = False) -> dict[str, Any]:
        """Return a marker pooling design."""

    @abstractmethod
    def sweep(
        self,
        baselines: Sequence[Path],
        arms: Sequence[tuple[str, Path]],
    ) -> dict[str, Any]:
        """Attribute payload addresses to arms using recorded JSON payloads."""

    @abstractmethod
    def show(
        self,
        bundle_dir: Path,
        *,
        requests: bool = False,
        scripts: bool = False,
        probes: bool = False,
    ) -> dict[str, Any]:
        """Summarise a capture bundle."""
