"""Unit tests for CDP command routing, event collection and body fetching."""

from __future__ import annotations

import hashlib
import json
import queue
import time
import unittest
from typing import Any, Callable
from unittest import mock

from aio_reverse.adapters.web.cdp import response_bodies
from aio_reverse.adapters.web.cdp.cdp_channel import CdpChannel
from aio_reverse.adapters.web.cdp.chrome_cdp_session import ChromeCdpSession
from aio_reverse.adapters.web.cdp.page_targets import select_page
from aio_reverse.adapters.web.cdp.response_bodies import collect_bodies
from aio_reverse.adapters.web.cdp.turn_collector import TurnCollector
from aio_reverse.application.ports.browser_session_port import TurnCapture
from aio_reverse.domain.errors import BrowserSessionError, ProbeUnavailableError


def event(method: str, **params: Any) -> dict[str, Any]:
    return {"method": method, "params": params}


class FakeTransport:
    """In-memory transport with optional automatic command replies."""

    def __init__(
        self,
        responder: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> None:
        self.responder = responder
        self.sent: list[dict[str, Any]] = []
        self.incoming: queue.Queue[Any] = queue.Queue()
        self.closed = False

    def send(self, message: str) -> None:
        payload = json.loads(message)
        self.sent.append(payload)
        if self.responder is not None:
            reply = self.responder(payload)
            if reply is not None:
                self.incoming.put(json.dumps(reply))

    def push(self, message: str | dict[str, Any]) -> None:
        self.incoming.put(
            message if isinstance(message, str) else json.dumps(message)
        )

    def recv(self) -> str:
        item = self.incoming.get(timeout=5)
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self) -> None:
        self.closed = True
        self.incoming.put(ConnectionError("transport closed"))


class StubChannel:
    """Command sender stub used to exercise body collection."""

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        assert params is not None
        self.calls.append((method, params))
        response = self.responses[params["requestId"]]
        if isinstance(response, BaseException):
            raise response
        return response

    def ensure_usable(self) -> None:
        return


class EvalChannel:
    """Channel stub that answers Runtime.evaluate and records every command."""

    def __init__(self, value: Any) -> None:
        self.value = value
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        self.calls.append((method, dict(params or {})))
        if method == "Runtime.evaluate":
            return {"result": {"type": "object", "value": self.value}}
        return {}

    def ensure_usable(self) -> None:
        return

    def close(self) -> None:
        return


def wait_failure(channel: CdpChannel) -> BrowserSessionError:
    for _ in range(400):
        try:
            channel.ensure_usable()
        except BrowserSessionError as error:
            return error
        time.sleep(0.005)
    raise AssertionError("channel did not fail")


class CdpChannelTest(unittest.TestCase):
    def make_channel(
        self,
        responder: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> tuple[CdpChannel, FakeTransport, list[dict[str, Any]]]:
        transport = FakeTransport(responder)
        events: list[dict[str, Any]] = []
        channel = CdpChannel(transport, events.append)
        self.addCleanup(channel.close)
        return channel, transport, events

    def test_command_roundtrip(self) -> None:
        channel, transport, _ = self.make_channel(
            lambda message: {"id": message["id"], "result": {"value": 7}}
        )

        result = channel.send("Runtime.evaluate", {"expression": "7"})

        self.assertEqual(result, {"value": 7})
        self.assertEqual(transport.sent[0]["method"], "Runtime.evaluate")
        self.assertEqual(transport.sent[0]["id"], 1)

    def test_events_reach_the_callback(self) -> None:
        channel, transport, events = self.make_channel()
        transport.push(
            {"method": "Network.loadingFinished", "params": {"requestId": "1"}}
        )

        deadline = time.monotonic() + 2
        while not events and time.monotonic() < deadline:
            time.sleep(0.005)

        self.assertEqual(events[0]["method"], "Network.loadingFinished")
        self.assertEqual(events[0]["params"], {"requestId": "1"})

    def test_error_response_is_loud(self) -> None:
        channel, _, _ = self.make_channel(
            lambda message: {
                "id": message["id"],
                "error": {"code": -32000, "message": "boom"},
            }
        )

        with self.assertRaises(BrowserSessionError) as caught:
            channel.send("Page.enable")

        self.assertIn("Page.enable", str(caught.exception))
        self.assertIn("boom (code -32000)", str(caught.exception))

    def test_timeout_keeps_late_response_harmless(self) -> None:
        channel, transport, _ = self.make_channel()

        with self.assertRaises(BrowserSessionError) as caught:
            channel.send("Page.enable", timeout_s=0.05)
        self.assertIn("timed out", str(caught.exception))

        transport.responder = lambda message: {
            "id": message["id"],
            "result": {"ok": True},
        }
        transport.push({"id": 1, "result": {}})

        self.assertEqual(
            channel.send("Runtime.enable"), {"ok": True}
        )

    def test_invalid_json_fails_the_channel(self) -> None:
        channel, transport, _ = self.make_channel()
        transport.push("this is not json")

        error = wait_failure(channel)

        self.assertIn("invalid JSON", str(error))

    def test_callback_failure_fails_the_channel(self) -> None:
        transport = FakeTransport()
        channel = CdpChannel(
            transport,
            lambda _event: (_ for _ in ()).throw(RuntimeError("collector bug")),
        )
        self.addCleanup(channel.close)
        transport.push({"method": "Network.loadingFinished", "params": {}})

        error = wait_failure(channel)

        self.assertIn("collector bug", str(error))

    def test_unknown_response_id_fails_the_channel(self) -> None:
        channel, transport, _ = self.make_channel()
        transport.push({"id": 99, "result": {}})

        error = wait_failure(channel)

        self.assertIn("unknown command id", str(error))


class SelectPageTest(unittest.TestCase):
    def targets(self) -> list[dict[str, Any]]:
        return [
            {"type": "service_worker", "url": "https://chatgpt.com/sw.js"},
            {
                "type": "page",
                "url": "https://example.test/",
                "webSocketDebuggerUrl": "ws://example",
            },
            {
                "type": "page",
                "url": "https://chatgpt.com/c/1",
                "webSocketDebuggerUrl": "ws://chatgpt",
            },
        ]

    def test_prefix_selects_matching_page(self) -> None:
        chosen = select_page(self.targets(), "https://chatgpt.com")
        self.assertEqual(chosen["webSocketDebuggerUrl"], "ws://chatgpt")

    def test_exact_url_wins_over_older_tabs(self) -> None:
        targets = [
            {
                "type": "page",
                "url": "https://chatgpt.com/c/old",
                "webSocketDebuggerUrl": "ws://old",
            },
            {
                "type": "page",
                "url": "https://chatgpt.com/",
                "webSocketDebuggerUrl": "ws://home",
            },
        ]

        chosen = select_page(targets, "https://chatgpt.com")

        self.assertEqual(chosen["webSocketDebuggerUrl"], "ws://home")

    def test_prefix_without_match_returns_none(self) -> None:
        self.assertIsNone(select_page(self.targets(), "https://missing.test"))

    def test_prefix_without_match_can_fall_back(self) -> None:
        chosen = select_page(
            self.targets(), "https://missing.test", fallback=True
        )
        self.assertEqual(chosen["webSocketDebuggerUrl"], "ws://example")

    def test_without_prefix_selects_first_page(self) -> None:
        chosen = select_page(self.targets(), None)
        self.assertEqual(chosen["webSocketDebuggerUrl"], "ws://example")

    def test_empty_targets(self) -> None:
        self.assertIsNone(select_page([], "https://chatgpt.com"))


class TurnCollectorTest(unittest.TestCase):
    def test_records_network_console_and_streams(self) -> None:
        collector = TurnCollector()
        collector.begin()
        before = collector.last_network_activity()
        time.sleep(0.01)

        collector.absorb(
            event(
                "Network.requestWillBeSent",
                requestId="1",
                type="Fetch",
                timestamp=1.0,
                request={
                    "url": "https://chatgpt.com/backend-api/conversation",
                    "method": "POST",
                    "headers": {"content-type": "application/json"},
                    "postData": "{}",
                },
                initiator={
                    "type": "script",
                    "stack": {
                        "callFrames": [
                            {
                                "functionName": "send",
                                "url": "https://chatgpt.com/app.js",
                                "lineNumber": 1,
                                "columnNumber": 2,
                            }
                        ]
                    },
                },
            )
        )
        collector.absorb(
            event(
                "Network.requestWillBeSentExtraInfo",
                requestId="1",
                headers={"Cookie": "session=abc"},
            )
        )
        collector.absorb(
            event(
                "Network.responseReceived",
                requestId="1",
                type="Fetch",
                timestamp=2.0,
                response={
                    "url": "https://chatgpt.com/backend-api/conversation",
                    "status": 200,
                    "statusText": "OK",
                    "headers": {"content-type": "text/event-stream"},
                    "mimeType": "text/event-stream",
                    "protocol": "h2",
                    "remoteIPAddress": "1.2.3.4",
                },
            )
        )
        collector.absorb(
            event(
                "Network.responseReceivedExtraInfo",
                requestId="1",
                headers={"set-cookie": "x=y"},
            )
        )
        collector.absorb(
            event(
                "Network.loadingFinished",
                requestId="1",
                timestamp=3.0,
                encodedDataLength=42,
            )
        )
        collector.absorb(
            event(
                "Network.eventSourceMessageReceived",
                requestId="1",
                eventName="delta",
                data="hello",
                timestamp=4.0,
            )
        )
        collector.absorb(
            event(
                "Network.webSocketFrameReceived",
                requestId="2",
                timestamp=5.0,
                response={"opcode": 1, "payloadData": "frame"},
            )
        )
        collector.absorb(
            event(
                "Runtime.consoleAPICalled",
                type="error",
                timestamp=6.0,
                args=[
                    {"type": "string", "value": "bad"},
                    {"type": "number", "unserializableValue": "NaN"},
                ],
                stack={
                    "callFrames": [
                        {
                            "functionName": "log",
                            "url": "https://chatgpt.com/app.js",
                            "lineNumber": 3,
                            "columnNumber": 4,
                        }
                    ]
                },
            )
        )
        collector.absorb(
            event(
                "Runtime.exceptionThrown",
                timestamp=7.0,
                exceptionDetails={
                    "text": "Uncaught",
                    "url": "https://chatgpt.com/app.js",
                    "lineNumber": 8,
                    "columnNumber": 9,
                    "exception": {"type": "object", "description": "Error: boom"},
                    "stack": {
                        "callFrames": [
                            {
                                "functionName": "run",
                                "url": "https://chatgpt.com/app.js",
                                "lineNumber": 8,
                                "columnNumber": 9,
                            }
                        ]
                    },
                },
            )
        )

        capture = collector.snapshot()

        self.assertEqual(len(capture.requests), 1)
        request = capture.requests[0]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["status"], 200)
        self.assertIsNone(request["request_body"])
        self.assertEqual(request["request_body_bytes"], 2)
        self.assertEqual(
            request["request_body_sha256"],
            hashlib.sha256(b"{}").hexdigest(),
        )
        self.assertEqual(
            request["request_headers_extra"], {"Cookie": "[redacted]"}
        )
        self.assertEqual(
            request["response_headers_extra"], {"set-cookie": "[redacted]"}
        )
        self.assertEqual(request["finished_at"], 3.0)
        self.assertEqual(request["encoded_data_length"], 42)
        self.assertFalse(request["orphan"])
        self.assertEqual(request["initiator"], "script")
        self.assertEqual(request["initiator_url"], "https://chatgpt.com/app.js")

        self.assertEqual(len(capture.sse_events), 1)
        self.assertNotIn("data", capture.sse_events[0])
        self.assertEqual(capture.sse_events[0]["data_bytes"], 5)
        self.assertEqual(
            capture.sse_events[0]["data_sha256"],
            hashlib.sha256(b"hello").hexdigest(),
        )
        self.assertEqual(len(capture.ws_frames), 1)
        self.assertNotIn("payload", capture.ws_frames[0])
        self.assertEqual(capture.ws_frames[0]["payload_bytes"], 5)
        self.assertEqual(
            capture.ws_frames[0]["payload_sha256"],
            hashlib.sha256(b"frame").hexdigest(),
        )
        self.assertEqual(
            capture.console[0]["args"], ["bad", "NaN"]
        )
        self.assertEqual(
            capture.console[0]["stack"][0]["function"], "log"
        )
        self.assertEqual(
            capture.exceptions[0]["exception"], "Error: boom"
        )
        self.assertGreater(capture.started_at, 0)
        self.assertGreaterEqual(capture.ended_at, capture.started_at)
        self.assertGreater(collector.last_network_activity(), before)

    def test_sensitive_headers_are_redacted_case_insensitively(self) -> None:
        collector = TurnCollector()
        collector.begin()
        collector.absorb(
            event(
                "Network.requestWillBeSent",
                requestId="1",
                request={
                    "url": "https://example.test/api",
                    "method": "GET",
                    "headers": {
                        "Cookie": "session=abc",
                        "AUTHORIZATION": "Bearer token",
                        "content-type": "application/json",
                    },
                },
            )
        )
        collector.absorb(
            event(
                "Network.requestWillBeSentExtraInfo",
                requestId="1",
                headers={"Proxy-Authorization": "Basic abc"},
            )
        )
        collector.absorb(
            event(
                "Network.responseReceived",
                requestId="1",
                response={
                    "url": "https://example.test/api",
                    "status": 200,
                    "headers": {"Set-Cookie": "x=y", "mime-type": "text/html"},
                },
            )
        )
        collector.absorb(
            event(
                "Network.responseReceivedExtraInfo",
                requestId="1",
                headers={"set-cookie": "x=y"},
            )
        )

        request = collector.snapshot().requests[0]

        self.assertEqual(
            request["request_headers"],
            {
                "Cookie": "[redacted]",
                "AUTHORIZATION": "[redacted]",
                "content-type": "application/json",
            },
        )
        self.assertEqual(
            request["request_headers_extra"],
            {"Proxy-Authorization": "[redacted]"},
        )
        self.assertEqual(
            request["response_headers"],
            {"Set-Cookie": "[redacted]", "mime-type": "text/html"},
        )
        self.assertEqual(
            request["response_headers_extra"], {"set-cookie": "[redacted]"}
        )

    def test_body_capture_patterns_keep_matching_bodies(self) -> None:
        collector = TurnCollector(("/backend-api/",))
        collector.begin()
        collector.absorb(
            event(
                "Network.requestWillBeSent",
                requestId="1",
                request={
                    "url": "https://example.test/backend-api/conversation",
                    "method": "POST",
                    "postData": '{"prompt":"hi"}',
                },
            )
        )
        collector.absorb(
            event(
                "Network.requestWillBeSent",
                requestId="2",
                request={
                    "url": "https://example.test/assets/telemetry",
                    "method": "POST",
                    "postData": '{"other":1}',
                },
            )
        )

        first, second = collector.snapshot().requests

        self.assertEqual(first["request_body"], '{"prompt":"hi"}')
        self.assertEqual(first["request_body_bytes"], 15)
        self.assertIsNone(second["request_body"])
        self.assertEqual(second["request_body_bytes"], 11)

    def test_stream_payloads_opt_in_keeps_raw_data(self) -> None:
        collector = TurnCollector(stream_payloads=True)
        collector.begin()
        collector.absorb(
            event(
                "Network.eventSourceMessageReceived",
                requestId="1",
                data="hello",
                timestamp=1.0,
            )
        )
        collector.absorb(
            event(
                "Network.webSocketFrameReceived",
                requestId="2",
                timestamp=2.0,
                response={"opcode": 1, "payloadData": "frame"},
            )
        )

        capture = collector.snapshot()

        self.assertEqual(capture.sse_events[0]["data"], "hello")
        self.assertEqual(
            capture.sse_events[0]["data_sha256"],
            hashlib.sha256(b"hello").hexdigest(),
        )
        self.assertEqual(capture.ws_frames[0]["payload"], "frame")
        self.assertEqual(
            capture.ws_frames[0]["payload_sha256"],
            hashlib.sha256(b"frame").hexdigest(),
        )

    def test_response_without_request_is_kept_as_orphan(self) -> None:
        collector = TurnCollector()
        collector.begin()
        collector.absorb(
            event(
                "Network.responseReceived",
                requestId="9",
                response={
                    "url": "https://chatgpt.com/backend-api/late",
                    "status": 204,
                    "headers": {},
                },
            )
        )

        request = collector.snapshot().requests[0]

        self.assertTrue(request["orphan"])
        self.assertEqual(
            request["url"], "https://chatgpt.com/backend-api/late"
        )
        self.assertEqual(request["status"], 204)

    def test_malformed_event_is_loud(self) -> None:
        collector = TurnCollector()
        collector.begin()

        with self.assertRaises(BrowserSessionError):
            collector.absorb(
                event("Network.requestWillBeSent", requestId="1")
            )


class CollectBodiesTest(unittest.TestCase):
    def test_fetches_bodies_for_matching_requests(self) -> None:
        channel = StubChannel(
            {
                "1": {"body": "hello", "base64Encoded": False},
                "2": {"body": "aGk=", "base64Encoded": True},
            }
        )
        capture = TurnCapture(
            requests=[
                self.record("1", "https://chatgpt.com/backend-api/a"),
                self.record("2", "https://chatgpt.com/backend-api/b"),
                self.record("3", "https://chatgpt.com/assets/app.js"),
                self.record("4", "https://chatgpt.com/backend-api/c", finished=False),
            ]
        )

        collect_bodies(channel, capture, ("/backend-api/",))

        self.assertEqual(len(channel.calls), 2)
        first, second = capture.requests[0], capture.requests[1]
        self.assertEqual(first["body"], "hello")
        self.assertEqual(first["body_bytes"], 5)
        self.assertEqual(first["body_encoding"], "utf-8")
        self.assertEqual(second["body"], "aGk=")
        self.assertEqual(second["body_bytes"], 2)
        self.assertEqual(second["body_encoding"], "base64")
        self.assertNotIn("body", capture.requests[2])
        self.assertNotIn("body", capture.requests[3])

    def test_no_patterns_fetches_nothing(self) -> None:
        channel = StubChannel({})
        capture = TurnCapture(
            requests=[self.record("1", "https://chatgpt.com/backend-api/a")]
        )

        collect_bodies(channel, capture, ())

        self.assertEqual(channel.calls, [])
        self.assertNotIn("body", capture.requests[0])

    def test_command_failure_is_recorded(self) -> None:
        channel = StubChannel(
            {"1": BrowserSessionError("Network.getResponseBody failed: gone")}
        )
        capture = TurnCapture(
            requests=[self.record("1", "https://chatgpt.com/backend-api/a")]
        )

        collect_bodies(channel, capture, ("/backend-api/",))

        self.assertIn("gone", capture.requests[0]["body_error"])
        self.assertNotIn("body", capture.requests[0])

    def test_body_above_cap_is_rejected(self) -> None:
        channel = StubChannel(
            {"1": {"body": "hello", "base64Encoded": False}}
        )
        capture = TurnCapture(
            requests=[self.record("1", "https://chatgpt.com/backend-api/a")]
        )

        with mock.patch.object(response_bodies, "MAX_BODY_BYTES", 4):
            collect_bodies(channel, capture, ("/backend-api/",))

        self.assertIn("above the 4 byte cap", capture.requests[0]["body_error"])
        self.assertNotIn("body", capture.requests[0])

    def test_invalid_base64_is_recorded(self) -> None:
        channel = StubChannel(
            {"1": {"body": "**not base64**", "base64Encoded": True}}
        )
        capture = TurnCapture(
            requests=[self.record("1", "https://chatgpt.com/backend-api/a")]
        )

        collect_bodies(channel, capture, ("/backend-api/",))

        self.assertIn("invalid base64", capture.requests[0]["body_error"])

    def test_failed_requests_are_skipped(self) -> None:
        channel = StubChannel({})
        capture = TurnCapture(
            requests=[
                self.record(
                    "1", "https://chatgpt.com/backend-api/a", error="net::ERR"
                )
            ]
        )

        collect_bodies(channel, capture, ("/backend-api/",))

        self.assertEqual(channel.calls, [])

    def record(
        self, request_id: str, url: str, *, finished: bool = True, error: str | None = None
    ) -> dict[str, Any]:
        return {
            "id": request_id,
            "url": url,
            "finished_at": 1.0 if finished else None,
            "error_text": error,
        }


class ChromeCdpSessionTest(unittest.TestCase):
    def test_unattached_session_is_loud(self) -> None:
        session = ChromeCdpSession()
        self.addCleanup(session.close)

        with self.assertRaises(BrowserSessionError):
            session.evaluate("1")
        with self.assertRaises(BrowserSessionError):
            session.end_turn()

    def test_end_turn_passes_body_capture_patterns(self) -> None:
        session = ChromeCdpSession(("/backend-api/",))
        self.addCleanup(session.close)
        session._channel = EvalChannel(None)

        with mock.patch(
            "aio_reverse.adapters.web.cdp.chrome_cdp_session.collect_bodies"
        ) as collect:
            capture = session.end_turn()

        collect.assert_called_once()
        channel, captured, patterns = collect.call_args.args
        self.assertIs(channel, session._channel)
        self.assertIs(captured, capture)
        self.assertEqual(patterns, ("/backend-api/",))

    def test_drain_probe_returns_snapshot_and_calls_wre_drain(self) -> None:
        session = ChromeCdpSession()
        self.addCleanup(session.close)
        channel = EvalChannel({"reads": [{"path": "navigator.userAgent"}]})
        session._channel = channel

        snapshot = session.drain_probe()

        self.assertEqual(snapshot["reads"][0]["path"], "navigator.userAgent")
        method, params = channel.calls[0]
        self.assertEqual(method, "Runtime.evaluate")
        self.assertIn("__WRE.drain()", params["expression"])

    def test_drain_probe_without_probe_is_loud(self) -> None:
        session = ChromeCdpSession()
        self.addCleanup(session.close)
        session._channel = EvalChannel(None)

        with self.assertRaises(ProbeUnavailableError) as caught:
            session.drain_probe()
        self.assertIn("__WRE.drain()", str(caught.exception))

    def test_click_dispatches_at_the_first_rendered_point(self) -> None:
        session = ChromeCdpSession()
        self.addCleanup(session.close)
        channel = EvalChannel({"x": 10.0, "y": 20.0})
        session._channel = channel

        session.click('button[aria-label="Send"]')

        method, params = channel.calls[0]
        self.assertEqual(method, "Runtime.evaluate")
        self.assertIn("getBoundingClientRect", params["expression"])
        mouse = [item for item in channel.calls if item[0] == "Input.dispatchMouseEvent"]
        self.assertEqual(
            [params["type"] for _, params in mouse],
            ["mouseMoved", "mousePressed", "mouseReleased"],
        )
        for _, params in mouse:
            self.assertEqual((params["x"], params["y"]), (10.0, 20.0))

    def test_list_pages_requires_attach(self) -> None:
        session = ChromeCdpSession()
        self.addCleanup(session.close)

        with self.assertRaises(BrowserSessionError):
            session.list_pages()

    def test_press_dispatches_text_and_raw_keys(self) -> None:
        session = ChromeCdpSession()
        self.addCleanup(session.close)
        channel = EvalChannel(None)
        session._channel = channel

        session.press("Enter")
        session.press("Escape")

        types = [params["type"] for _, params in channel.calls]
        self.assertEqual(types, ["keyDown", "keyUp", "rawKeyDown", "keyUp"])
        self.assertEqual(channel.calls[0][1]["text"], "\r")
        self.assertEqual(channel.calls[2][1]["key"], "Escape")

    def test_press_rejects_unknown_key(self) -> None:
        session = ChromeCdpSession()
        self.addCleanup(session.close)

        with self.assertRaises(ValueError) as caught:
            session.press("F5")
        self.assertIn("Escape", str(caught.exception))

    def test_outer_html_returns_serialized_document(self) -> None:
        session = ChromeCdpSession()
        self.addCleanup(session.close)
        channel = EvalChannel("<html><body>hi</body></html>")
        session._channel = channel

        html = session.outer_html()

        self.assertEqual(html, "<html><body>hi</body></html>")
        method, params = channel.calls[0]
        self.assertEqual(method, "Runtime.evaluate")
        self.assertEqual(params["expression"], "document.documentElement.outerHTML")

    def test_outer_html_rejects_empty_or_non_string(self) -> None:
        for value in ("", None, {"a": 1}):
            session = ChromeCdpSession()
            self.addCleanup(session.close)
            session._channel = EvalChannel(value)

            with self.assertRaises(BrowserSessionError):
                session.outer_html()

    def test_outer_html_enforces_snapshot_size_limit(self) -> None:
        session = ChromeCdpSession()
        self.addCleanup(session.close)
        session._channel = EvalChannel("<html>x" * 100)

        with mock.patch(
            "aio_reverse.adapters.web.cdp.chrome_cdp_session.MAX_SNAPSHOT_BYTES",
            50,
        ):
            with self.assertRaises(BrowserSessionError) as caught:
                session.outer_html()

        self.assertIn("bytes", str(caught.exception))
        self.assertIn("50", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
