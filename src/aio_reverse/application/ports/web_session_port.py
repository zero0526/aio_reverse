"""Ports and data types shared by interactive web sessions and artifacts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from aio_reverse.application.ports.browser_session_port import TurnCapture
from aio_reverse.application.page_snapshot import PageSnapshot
from aio_reverse.targets.action_script import ActionScript
from aio_reverse.targets.web_target import WebTargetSpec


@dataclass(frozen=True)
class StepRecord:
    """Timing and result of one executed action."""

    index: int
    type: str
    started_at: float
    ended_at: float
    saved: str | None = None
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "type": self.type,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "saved": self.saved,
            "value": self.value,
        }


@dataclass(frozen=True)
class SessionTurn:
    """Everything captured while one action script ran."""

    script: str
    variables: dict[str, Any]
    steps: tuple[StepRecord, ...]
    capture: TurnCapture
    probe: dict[str, Any]
    page: dict[str, Any]
    env: dict[str, Any]
    started_at: float
    ended_at: float

    @property
    def duration_s(self) -> float:
        return self.ended_at - self.started_at


@dataclass(frozen=True)
class RunPaths:
    """Directories allocated for one run."""

    run_id: str
    run_dir: Path


@dataclass(frozen=True)
class SnapshotFile:
    """Metadata of one stored HTML snapshot; the HTML stays on disk."""

    label: str
    path: Path
    bytes: int
    sha256: str


class IWebSession(ABC):
    """A live target session used by use cases, CLI and MCP handover."""

    @property
    @abstractmethod
    def target(self) -> WebTargetSpec:
        """Return the target this session drives."""

    @abstractmethod
    def open(self) -> None:
        """Start or attach Chrome, navigate, verify login and inject the probe."""

    @abstractmethod
    def login(self, timeout_s: float = 300.0) -> dict[str, Any]:
        """Open the login page and wait for the human to sign in."""

    @abstractmethod
    def run_script(
        self,
        script: ActionScript,
        variables: Mapping[str, object] | None = None,
    ) -> SessionTurn:
        """Execute one script between begin_turn and end_turn."""

    @abstractmethod
    def click(self, selector: str) -> None:
        """Click an element in the live page."""

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Insert text into the focused element."""

    @abstractmethod
    def press(self, key: str) -> None:
        """Press a whitelisted key."""

    @abstractmethod
    def evaluate(self, expression: str) -> Any:
        """Evaluate an expression in the live page."""

    @abstractmethod
    def navigate(self, url: str) -> None:
        """Navigate the live page to an http(s) URL."""

    @abstractmethod
    def inject_probe(self) -> None:
        """Install and verify the Rust probe on the page."""

    @abstractmethod
    def dump_state(self) -> dict[str, Any]:
        """Return the current page info and environment snapshot."""

    @abstractmethod
    def capture_page(self, label: str) -> PageSnapshot:
        """Serialize the live document as an HTML snapshot under a label."""

    @abstractmethod
    def close(self, keep_browser: bool = True) -> None:
        """Detach from the page, optionally stopping Chrome."""


class IRunStore(ABC):
    """Persistence contract for run, turn and summary artifacts."""

    @abstractmethod
    def create_run(self, target_name: str) -> RunPaths:
        """Allocate a fresh run directory."""

    @abstractmethod
    def write_run(self, paths: RunPaths, payload: dict[str, Any]) -> None:
        """Write the run-level record."""

    @abstractmethod
    def write_turn(self, paths: RunPaths, index: int, turn: SessionTurn) -> None:
        """Write every artifact produced by one turn."""

    @abstractmethod
    def write_summary(self, paths: RunPaths, payload: dict[str, Any]) -> None:
        """Write the cross-turn summary."""


class IHtmlSnapshotStore(ABC):
    """Persistence contract for labelled HTML page snapshots."""

    @abstractmethod
    def write(self, target_name: str, label: str, html: str) -> SnapshotFile:
        """Store one snapshot under the target and return its metadata."""
