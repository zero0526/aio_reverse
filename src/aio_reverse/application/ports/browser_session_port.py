"""Port for driving a live browser page over CDP."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnCapture:
    """Everything observed between begin_turn and end_turn."""

    requests: list[dict[str, Any]] = field(default_factory=list)
    console: list[dict[str, Any]] = field(default_factory=list)
    exceptions: list[dict[str, Any]] = field(default_factory=list)
    sse_events: list[dict[str, Any]] = field(default_factory=list)
    ws_frames: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = 0.0
    ended_at: float = 0.0


class IBrowserSessionPort(ABC):
    """A single page target controlled through the Chrome DevTools Protocol."""

    @abstractmethod
    def attach(self, port: int, url_prefix: str | None = None) -> None:
        """Attach to a page target, creating one when no page matches."""

    @abstractmethod
    def list_pages(self) -> list[dict[str, Any]]:
        """Return the page targets exposed by the attached Chrome."""

    @abstractmethod
    def navigate(self, url: str, timeout_s: float = 60.0) -> None:
        """Navigate and wait for the load event."""

    @abstractmethod
    def reload(self, timeout_s: float = 60.0) -> None:
        """Reload the current page and wait for the load event."""

    @abstractmethod
    def evaluate(self, expression: str, timeout_s: float = 30.0) -> Any:
        """Evaluate an expression and return its JSON value."""

    @abstractmethod
    def insert_text(self, text: str) -> None:
        """Insert text as a trusted input event."""

    @abstractmethod
    def click(self, selector: str, timeout_s: float = 30.0) -> None:
        """Click an element with trusted mouse events."""

    @abstractmethod
    def press(self, key: str) -> None:
        """Press a key with a trusted keyboard event."""

    @abstractmethod
    def add_init_script(self, source: str) -> None:
        """Install a script that runs before every new document."""

    @abstractmethod
    def begin_turn(self) -> None:
        """Reset the event buffers before sending a prompt."""

    @abstractmethod
    def end_turn(self) -> TurnCapture:
        """Return the events collected since begin_turn."""

    @abstractmethod
    def drain_probe(self) -> dict[str, Any]:
        """Return and clear the Rust probe snapshot for the current turn."""

    @abstractmethod
    def snapshot_env(self, script: str) -> dict[str, Any]:
        """Evaluate the toolkit environment script and return its JSON result."""

    @abstractmethod
    def page_info(self) -> dict[str, Any]:
        """Return the current URL, title and document readiness."""

    @abstractmethod
    def outer_html(self) -> str:
        """Return the serialized outerHTML of the live document."""

    @abstractmethod
    def last_network_activity(self) -> float:
        """Return the monotonic timestamp of the last Network event."""

    @abstractmethod
    def close(self) -> None:
        """Detach from the page without shutting Chrome down."""
