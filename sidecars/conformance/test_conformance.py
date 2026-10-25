"""Runs the same protocol cases against the Node, C++ and Rust echo hosts."""

from __future__ import annotations

import os
import signal
import time
import unittest
from contextlib import contextmanager
from typing import Iterator

from aio_sidecar import (
    RETRYABLE_KINDS,
    BadInput,
    ErrorKind,
    InternalError,
    ProtocolError,
    SidecarAlert,
    Timeout,
    Unsupported,
    WreError,
    connect,
    schema_hash,
)

from hosts import ECHO_DESCRIPTOR, ERROR_KIND_CLASSES, EchoHost, require_hosts

OP_NAMES = [op["name"] for op in ECHO_DESCRIPTOR["ops"]]


def _client_id(host: EchoHost) -> str:
    return f"conformance-{host.name}"


@contextmanager
def _client(
    host: EchoHost,
    alerts: list[SidecarAlert],
    events: list | None = None,
) -> Iterator:
    client = connect(
        host.binary,
        client_id=_client_id(host),
        on_alert=alerts.append,
        on_event=events.append if events is not None else None,
    )
    try:
        yield client
    finally:
        client.close()


def _assert_alert(
    case: unittest.TestCase,
    alert: SidecarAlert,
    host: EchoHost,
    *,
    kind: str,
    op: str,
    target: str | None,
    session: str | None,
    phase: str = "call",
) -> None:
    case.assertEqual(alert.kind, kind)
    case.assertEqual(alert.op, op)
    case.assertEqual(alert.target, target)
    case.assertEqual(alert.session, session)
    case.assertEqual(alert.client_id, _client_id(host))
    case.assertEqual(alert.phase, phase)
    case.assertEqual(alert.binary, host.binary)
    case.assertIsNotNone(alert.pid)
    case.assertTrue(alert.occurred_at)
    case.assertIsInstance(alert.exception, WreError)
    case.assertEqual(alert.exception.kind, kind)


class EchoHostConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hosts = require_hosts()
        if not cls.hosts:
            raise unittest.SkipTest("no echo sidecar hosts are available")

    def test_handshake_and_descriptor(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                with _client(host, alerts) as client:
                    hello = client.hello
                    self.assertEqual(hello["protocol"], 1)
                    self.assertEqual(hello["bundle"], "aio")
                    self.assertEqual(hello["schema_hash"], schema_hash(ECHO_DESCRIPTOR))
                    self.assertEqual(hello["targets"], ["echo"])
                    self.assertEqual(hello["workers"], 1)
                    self.assertEqual(hello["pid"], client.pid)
                    self.assertEqual(client.targets(), ["echo"])
                    self.assertEqual(
                        client.describe()["clients"], [ECHO_DESCRIPTOR]
                    )
                self.assertEqual(alerts, [])

    def test_open_echo_config_and_stats(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                with _client(host, alerts) as client:
                    session = client.open("echo", {"flavor": host.name})
                    self.assertEqual(session.target, "echo")
                    self.assertEqual(session.ops, OP_NAMES)

                    value = f"xin chào {host.name} 🚀"
                    echoed = session.call("echo", {"value": value})
                    self.assertEqual(
                        echoed, {"value": value, "config": {"flavor": host.name}}
                    )

                    stats = session.call("stats")
                    self.assertEqual(stats["config"], {"flavor": host.name})
                    self.assertGreaterEqual(stats["calls"], 2)
                self.assertEqual(alerts, [])

    def test_events_are_enriched(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                global_events: list = []
                with _client(host, alerts, global_events) as client:
                    session = client.open("echo")
                    per_call: list = []
                    result = session.call(
                        "emit",
                        {"event": "progress", "data": {"step": 3}},
                        on_event=per_call.append,
                    )
                    self.assertEqual(
                        result, {"emitted": "progress", "data": {"step": 3}}
                    )
                    self.assertEqual(len(per_call), 1)
                    event = per_call[0]
                    self.assertGreater(event.call_id, 0)
                    self.assertEqual(event.event, "progress")
                    self.assertEqual(event.data, {"step": 3})
                    self.assertEqual(event.client_id, _client_id(host))
                    self.assertEqual(event.target, "echo")
                    self.assertEqual(event.op, "emit")
                    self.assertEqual(event.session, session.id)

                    self.assertTrue(
                        any(
                            item.event == "progress" and item.target is None
                            for item in global_events
                        )
                    )
                self.assertEqual(alerts, [])

    def test_binary_roundtrip(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                blob = bytes(range(256)) + b"\x00\xff\x10"
                with _client(host, alerts) as client:
                    session = client.open("echo")
                    payload, returned = session.call_with_binary(
                        "bytes", {}, bin_part=blob
                    )
                    self.assertEqual(payload, {"size": len(blob), "hex": blob.hex()})
                    self.assertEqual(returned, blob)
                self.assertEqual(alerts, [])

    def test_typed_errors_raise_alerts_first(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                with _client(host, alerts) as client:
                    session = client.open("echo")
                    for kind, error_class in ERROR_KIND_CLASSES.items():
                        with self.subTest(host=host.name, kind=kind):
                            start = len(alerts)
                            caught_error: WreError | None = None
                            try:
                                session.call(
                                    "fail",
                                    {
                                        "kind": kind,
                                        "message": f"boom {kind}",
                                        "detail": {"kind": kind},
                                    },
                                )
                            except error_class as error:
                                caught_error = error
                                seen = list(alerts[start:])
                                self.assertEqual(error.kind, kind)
                                self.assertEqual(error.detail, {"kind": kind})
                                self.assertEqual(
                                    error.retryable, kind in RETRYABLE_KINDS
                                )
                            else:
                                self.fail(f"expected {error_class.__name__}")

                            self.assertIsNotNone(caught_error)
                            self.assertTrue(
                                seen, "the alert must fire before the exception"
                            )
                            alert = seen[-1]
                            _assert_alert(
                                self,
                                alert,
                                host,
                                kind=kind,
                                op="fail",
                                target="echo",
                                session=session.id,
                            )
                            self.assertIs(alert.exception, caught_error)
                            self.assertEqual(
                                alert.retryable, kind in RETRYABLE_KINDS
                            )
                self.assertEqual(len(alerts), len(ERROR_KIND_CLASSES))

    def test_native_exception_becomes_internal(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                message = f"kaboom {host.name}"
                with _client(host, alerts) as client:
                    session = client.open("echo")
                    with self.assertRaises(InternalError) as caught:
                        session.call("throw", {"message": message})
                    error = caught.exception
                    self.assertEqual(error.kind, ErrorKind.INTERNAL)
                    self.assertIsInstance(error.detail, dict)
                    engine_exception = error.detail["engine_exception"]
                    self.assertEqual(engine_exception["message"], message)
                    self.assertTrue(engine_exception["type"])

                alert = alerts[-1]
                _assert_alert(
                    self,
                    alert,
                    host,
                    kind=ErrorKind.INTERNAL,
                    op="throw",
                    target="echo",
                    session=session.id,
                )

    def test_unknown_op_target_and_session(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                with _client(host, alerts) as client:
                    session = client.open("echo")

                    start = len(alerts)
                    with self.assertRaises(Unsupported):
                        session.call("nope")
                    _assert_alert(
                        self,
                        alerts[start],
                        host,
                        kind=ErrorKind.UNSUPPORTED,
                        op="nope",
                        target="echo",
                        session=session.id,
                    )

                    start = len(alerts)
                    with self.assertRaises(Unsupported):
                        client.open("nope")
                    _assert_alert(
                        self,
                        alerts[start],
                        host,
                        kind=ErrorKind.UNSUPPORTED,
                        op="open",
                        target="nope",
                        session=None,
                    )

                    start = len(alerts)
                    with self.assertRaises(BadInput):
                        client.call("echo", {"value": 1})
                    _assert_alert(
                        self,
                        alerts[start],
                        host,
                        kind=ErrorKind.BAD_INPUT,
                        op="echo",
                        target=None,
                        session=None,
                    )

                    start = len(alerts)
                    with self.assertRaises(BadInput):
                        client.call("echo", {"value": 1}, session="s999")
                    _assert_alert(
                        self,
                        alerts[start],
                        host,
                        kind=ErrorKind.BAD_INPUT,
                        op="echo",
                        target=None,
                        session="s999",
                    )

    def test_deadline_reports_timeout(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                with _client(host, alerts) as client:
                    session = client.open("echo")
                    started = time.monotonic()
                    with self.assertRaises(Timeout) as caught:
                        session.call("sleep", {"ms": 1000}, deadline_ms=100)
                    elapsed = time.monotonic() - started
                    self.assertEqual(caught.exception.kind, ErrorKind.TIMEOUT)
                    self.assertTrue(caught.exception.retryable)
                    self.assertLess(elapsed, 2.5)

                alert = alerts[-1]
                _assert_alert(
                    self,
                    alert,
                    host,
                    kind=ErrorKind.TIMEOUT,
                    op="sleep",
                    target="echo",
                    session=session.id,
                )

    def test_health_warmup_diag_and_metrics(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                with _client(host, alerts) as client:
                    session = client.open("echo")

                    health = session.health()
                    self.assertIs(health["ok"], True)
                    self.assertEqual(health["target"], "echo")

                    self.assertEqual(session.warmup(), {"warm": True})

                    diag = client.call("diag", session=session.id)
                    self.assertEqual(diag["mode"], "off")
                    self.assertEqual(diag["target"], "echo")
                    self.assertIsNone(diag["path"])
                    self.assertIsInstance(diag["report"], dict)

                    metrics = client.metrics()
                    for key in (
                        "requests",
                        "calls",
                        "errors",
                        "events",
                        "sessions_opened",
                        "sessions_open",
                    ):
                        self.assertIn(key, metrics)
                    self.assertEqual(metrics["sessions_opened"], 1)
                    self.assertEqual(metrics["sessions_open"], 1)
                    self.assertGreaterEqual(metrics["events"], 1)
                self.assertEqual(alerts, [])

    def test_close_and_shutdown(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                with _client(host, alerts) as client:
                    session = client.open("echo")
                    session.close()

                    start = len(alerts)
                    with self.assertRaises(BadInput):
                        session.call("echo", {"value": 1})
                    _assert_alert(
                        self,
                        alerts[start],
                        host,
                        kind=ErrorKind.BAD_INPUT,
                        op="echo",
                        target="echo",
                        session=session.id,
                    )

                    client.shutdown()
                    start = len(alerts)
                    with self.assertRaises(ProtocolError):
                        client.call("hello")
                    _assert_alert(
                        self,
                        alerts[start],
                        host,
                        kind=ErrorKind.PROTOCOL,
                        op="hello",
                        target=None,
                        session=None,
                    )

    def test_killed_host_reports_protocol_error(self) -> None:
        if os.name == "nt":
            self.skipTest("signal-based kill is POSIX only")
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                client = connect(
                    host.binary,
                    client_id=_client_id(host),
                    on_alert=alerts.append,
                )
                try:
                    client.open("echo")
                    os.kill(client.pid, signal.SIGKILL)
                    with self.assertRaises(ProtocolError):
                        client.call("hello")
                finally:
                    client.close()

                alert = alerts[-1]
                _assert_alert(
                    self,
                    alert,
                    host,
                    kind=ErrorKind.PROTOCOL,
                    op="hello",
                    target=None,
                    session=None,
                )


if __name__ == "__main__":
    unittest.main()
