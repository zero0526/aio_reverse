"""CDP-backed browser session for one live page target."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Sequence

from aio_reverse.adapters.web.cdp.cdp_channel import CdpChannel
from aio_reverse.adapters.web.cdp.cdp_values import remote_value
from aio_reverse.adapters.web.cdp.page_targets import (
    list_page_targets,
    open_page_target,
    select_page,
)
from aio_reverse.adapters.web.cdp.response_bodies import collect_bodies
from aio_reverse.adapters.web.cdp.turn_collector import TurnCollector
from aio_reverse.adapters.web.cdp.websocket_transport import WebSocketTransport
from aio_reverse.application.page_element_expressions import (
    first_visible_click_point_expression,
)
from aio_reverse.application.ports.browser_session_port import (
    IBrowserSessionPort,
    TurnCapture,
)
from aio_reverse.domain.errors import BrowserSessionError, ProbeUnavailableError


@dataclass(frozen=True)
class _KeySpec:
    key: str
    code: str
    virtual_key: int
    text: str | None


KEY_SPECS: dict[str, _KeySpec] = {
    "Enter": _KeySpec("Enter", "Enter", 13, "\r"),
    "Escape": _KeySpec("Escape", "Escape", 27, None),
    "Tab": _KeySpec("Tab", "Tab", 9, None),
    "Backspace": _KeySpec("Backspace", "Backspace", 8, None),
}

_DRAIN_PROBE = (
    "(() => {"
    "  if (typeof window.__WRE === 'undefined' || !window.__WRE"
    "      || typeof window.__WRE.drain !== 'function') return null;"
    "  return window.__WRE.drain();"
    "})()"
)

MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024


class ChromeCdpSession(IBrowserSessionPort):
    """A page target driven over CDP with trusted input and per-turn capture."""

    def __init__(
        self,
        body_capture_patterns: Sequence[str] = (),
        *,
        stream_payloads: bool = False,
        host: str = "127.0.0.1",
    ) -> None:
        self._host = host
        self._body_capture_patterns = tuple(body_capture_patterns)
        self._collector = TurnCollector(
            self._body_capture_patterns, stream_payloads
        )
        self._channel: CdpChannel | None = None
        self._target: dict[str, Any] | None = None
        self._port: int | None = None

    def attach(self, port: int, url_prefix: str | None = None) -> None:
        self._port = port
        targets = list_page_targets(self._host, port)
        target = select_page(targets, url_prefix, fallback=True)
        if target is None:
            target = open_page_target(self._host, port)

        websocket_url = target.get("webSocketDebuggerUrl")
        if not isinstance(websocket_url, str) or not websocket_url:
            raise BrowserSessionError(
                f"page target has no webSocketDebuggerUrl: {target.get('url')!r}"
            )

        self._detach()
        transport = WebSocketTransport(websocket_url)
        channel = CdpChannel(transport, self._collector.absorb)
        try:
            channel.send(
                "Network.enable",
                {
                    "maxTotalBufferSize": 100 * 1024 * 1024,
                    "maxResourceBufferSize": 10 * 1024 * 1024,
                    "maxPostDataSize": 5 * 1024 * 1024,
                },
            )
            channel.send("Page.enable")
            channel.send("Runtime.enable")
            channel.send("Network.setCacheDisabled", {"cacheDisabled": True})
        except BaseException:
            channel.close()
            raise

        self._channel = channel
        self._target = target

    def list_pages(self) -> list[dict[str, Any]]:
        if self._port is None:
            raise BrowserSessionError(
                "CDP session is not attached; call attach() first"
            )
        return list_page_targets(self._host, self._port)

    def navigate(self, url: str, timeout_s: float = 60.0) -> None:
        result = self._require_channel().send(
            "Page.navigate", {"url": url}, timeout_s=timeout_s
        )
        error_text = result.get("errorText")
        if error_text:
            raise BrowserSessionError(
                f"navigation to {url} failed: {error_text}"
            )
        self._wait_ready(timeout_s, f"after navigating to {url}")

    def reload(self, timeout_s: float = 60.0) -> None:
        self._require_channel().send("Page.reload", timeout_s=timeout_s)
        self._wait_ready(timeout_s, "after reload")

    def evaluate(self, expression: str, timeout_s: float = 30.0) -> Any:
        response = self._require_channel().send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
            timeout_s=timeout_s,
        )

        details = response.get("exceptionDetails")
        if details is not None:
            if not isinstance(details, dict):
                raise BrowserSessionError(
                    "Runtime.evaluate returned non-object exceptionDetails"
                )
            raise BrowserSessionError(
                f"JavaScript evaluation failed: {_exception_text(details)}"
            )

        result = response.get("result")
        if not isinstance(result, dict):
            raise BrowserSessionError(
                "Runtime.evaluate returned no result object"
            )
        if result.get("type") == "undefined":
            return None
        if "value" in result:
            return result["value"]
        if "unserializableValue" in result:
            return result["unserializableValue"]
        raise BrowserSessionError(
            f"Runtime.evaluate returned no JSON value: {json.dumps(result)}"
        )

    def insert_text(self, text: str) -> None:
        self._require_channel().send("Input.insertText", {"text": text})

    def click(self, selector: str, timeout_s: float = 30.0) -> None:
        point = self.evaluate(
            first_visible_click_point_expression(selector),
            timeout_s=timeout_s,
        )
        if not isinstance(point, dict) or not isinstance(
            point.get("x"), (int, float)
        ) or not isinstance(point.get("y"), (int, float)):
            raise BrowserSessionError(
                f"click point for {selector} is invalid: {point!r}"
            )

        channel = self._require_channel()
        x, y = float(point["x"]), float(point["y"])
        channel.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseMoved",
                "x": x,
                "y": y,
                "button": "none",
                "buttons": 0,
            },
        )
        channel.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": "left",
                "buttons": 1,
                "clickCount": 1,
            },
        )
        channel.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": "left",
                "buttons": 0,
                "clickCount": 1,
            },
        )

    def press(self, key: str) -> None:
        spec = KEY_SPECS.get(key)
        if spec is None:
            raise ValueError(
                f"unsupported key {key!r}; expected one of {sorted(KEY_SPECS)}"
            )
        channel = self._require_channel()
        base = {
            "key": spec.key,
            "code": spec.code,
            "windowsVirtualKeyCode": spec.virtual_key,
            "nativeVirtualKeyCode": spec.virtual_key,
        }
        if spec.text is None:
            channel.send(
                "Input.dispatchKeyEvent", {**base, "type": "rawKeyDown"}
            )
        else:
            channel.send(
                "Input.dispatchKeyEvent",
                {
                    **base,
                    "type": "keyDown",
                    "text": spec.text,
                    "unmodifiedText": spec.text,
                },
            )
        channel.send("Input.dispatchKeyEvent", {**base, "type": "keyUp"})

    def add_init_script(self, source: str) -> None:
        self._require_channel().send(
            "Page.addScriptToEvaluateOnNewDocument", {"source": source}
        )

    def begin_turn(self) -> None:
        self._collector.begin()

    def end_turn(self) -> TurnCapture:
        capture = self._collector.snapshot()
        collect_bodies(
            self._require_channel(), capture, self._body_capture_patterns
        )
        return capture

    def last_network_activity(self) -> float:
        return self._collector.last_network_activity()

    def drain_probe(self) -> dict[str, Any]:
        value = self.evaluate(_DRAIN_PROBE)
        if value is None:
            raise ProbeUnavailableError(
                "__WRE.drain() is unavailable; inject the Rust probe before draining"
            )
        if not isinstance(value, dict):
            raise BrowserSessionError(
                f"__WRE.drain() returned {type(value).__name__}, expected an object"
            )
        return value

    def snapshot_env(self, script: str) -> dict[str, Any]:
        value = self.evaluate(script, timeout_s=120)
        if not isinstance(value, dict):
            raise BrowserSessionError(
                f"env script returned {type(value).__name__}, expected an object"
            )
        return value

    def page_info(self) -> dict[str, Any]:
        value = self.evaluate(
            "({url: location.href, title: document.title,"
            " ready_state: document.readyState})"
        )
        if not isinstance(value, dict):
            raise BrowserSessionError(
                f"page info returned {type(value).__name__}, expected an object"
            )
        return value

    def outer_html(self) -> str:
        value = self.evaluate(
            "document.documentElement.outerHTML", timeout_s=60
        )
        if not isinstance(value, str) or not value:
            raise BrowserSessionError(
                f"outerHTML returned {type(value).__name__}, expected a non-empty string"
            )
        size = len(value.encode("utf-8"))
        if size > MAX_SNAPSHOT_BYTES:
            raise BrowserSessionError(
                f"document outerHTML is {size} bytes, above the "
                f"{MAX_SNAPSHOT_BYTES} byte snapshot limit; capture a smaller "
                "region with web evaluate instead"
            )
        return value

    def close(self) -> None:
        self._detach()

    def _wait_ready(self, timeout_s: float, context: str) -> None:
        deadline = time.monotonic() + timeout_s
        last_error: BrowserSessionError | None = None
        while True:
            channel = self._require_channel()
            channel.ensure_usable()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                state = self.evaluate(
                    "document.readyState", timeout_s=min(10.0, remaining)
                )
            except BrowserSessionError as error:
                last_error = error
            else:
                if state == "complete":
                    return
            time.sleep(0.1)
        raise BrowserSessionError(
            f"page did not reach readyState 'complete' within {timeout_s}s "
            f"{context}"
        ) from last_error

    def _require_channel(self) -> CdpChannel:
        if self._channel is None:
            raise BrowserSessionError(
                "CDP session is not attached; call attach() first"
            )
        return self._channel

    def _detach(self) -> None:
        channel = self._channel
        self._channel = None
        self._target = None
        if channel is not None:
            channel.close()


def _exception_text(details: dict[str, Any]) -> str:
    text = details.get("text")
    message = text if isinstance(text, str) else "evaluation failed"
    exception = details.get("exception")
    if isinstance(exception, dict):
        description = remote_value(exception, "Runtime.evaluate")
        if description is not None:
            return f"{message}: {description}"
    return message
