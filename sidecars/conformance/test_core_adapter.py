"""Tests the core sidecar adapter against the echo engines and its mapping."""

from __future__ import annotations

import os
import signal
import unittest

from aio_sidecar import ErrorKind, ProtocolError, SidecarAlert, Timeout, Unsupported
from aio_reverse.adapters.sidecar import SidecarSandboxAdapter, map_sidecar_error
from aio_reverse.domain.errors import (
    EmulationFailureError,
    SandboxResourceLimitError,
    TimeoutError,
)

from hosts import ERROR_KIND_CLASSES, require_hosts


class SidecarMappingTest(unittest.TestCase):
    def test_kinds_map_to_domain_errors(self) -> None:
        for kind, error_class in ERROR_KIND_CLASSES.items():
            with self.subTest(kind=kind):
                error = error_class(
                    f"boom {kind}", op="execute", target="echo"
                )
                mapped = map_sidecar_error(error)
                if kind in (ErrorKind.TIMEOUT, ErrorKind.CANCELLED):
                    self.assertIsInstance(mapped, TimeoutError)
                elif kind == ErrorKind.RESOURCE:
                    self.assertIsInstance(mapped, SandboxResourceLimitError)
                else:
                    self.assertIsInstance(mapped, EmulationFailureError)
                self.assertIn(kind, str(mapped))

    def test_non_text_input_is_rejected(self) -> None:
        adapter = SidecarSandboxAdapter("/nonexistent/sidecar")
        with self.assertRaises(TypeError):
            adapter.execute_snippet(123, "main", [])  # type: ignore[arg-type]


class CoreAdapterConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hosts = require_hosts()
        if not cls.hosts:
            raise unittest.SkipTest("no echo sidecar hosts are available")

    def test_execute_text_and_binary(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                with SidecarSandboxAdapter(
                    host.binary,
                    client_id=f"core-{host.name}",
                    on_alert=alerts.append,
                ) as adapter:
                    text = adapter.execute_snippet(
                        "print(1)",
                        "main",
                        ["--flag"],
                        {"k": "v"},
                        timeout_ms=2000,
                        memory_limit_mb=32,
                    )
                    self.assertEqual(text["entrypoint"], "main")
                    self.assertEqual(text["arguments"], ["--flag"])
                    self.assertEqual(text["environment"], {"k": "v"})
                    self.assertEqual(text["source_kind"], "text")
                    self.assertEqual(text["source"], "print(1)")
                    self.assertEqual(text["memory_limit_mb"], 32)

                    binary = adapter.execute_snippet(
                        b"\x00\x01\xff",
                        "blob",
                        [],
                        None,
                        timeout_ms=2000,
                        memory_limit_mb=16,
                    )
                    self.assertEqual(binary["entrypoint"], "blob")
                    self.assertEqual(binary["source_kind"], "binary")
                    self.assertIsNone(binary["source"])
                    self.assertEqual(binary["memory_limit_mb"], 16)
                self.assertEqual(alerts, [])

    def test_unknown_op_maps_and_alerts(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                adapter = SidecarSandboxAdapter(
                    host.binary,
                    op="nope",
                    client_id=f"core-{host.name}",
                    on_alert=alerts.append,
                )
                try:
                    with self.assertRaises(EmulationFailureError) as caught:
                        adapter.execute_snippet("x", "main", [])
                finally:
                    adapter.close()

                self.assertIsInstance(caught.exception.__cause__, Unsupported)
                alert = alerts[-1]
                self.assertEqual(alert.kind, ErrorKind.UNSUPPORTED)
                self.assertEqual(alert.op, "nope")
                self.assertEqual(alert.target, "echo")
                self.assertEqual(alert.session, "s1")
                self.assertEqual(alert.phase, "call")
                self.assertEqual(alert.client_id, f"core-{host.name}")

    def test_missing_result_fails_loud(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                adapter = SidecarSandboxAdapter(
                    host.binary,
                    op="stats",
                    client_id=f"core-{host.name}",
                    on_alert=alerts.append,
                )
                try:
                    with self.assertRaises(EmulationFailureError) as caught:
                        adapter.execute_snippet("x", "main", [])
                finally:
                    adapter.close()

                self.assertIn("returned no result", str(caught.exception))
                self.assertIsNone(caught.exception.__cause__)
                self.assertEqual(alerts, [])

    def test_timeout_maps_to_domain_timeout(self) -> None:
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                adapter = SidecarSandboxAdapter(
                    host.binary,
                    op="sleep",
                    client_id=f"core-{host.name}",
                    on_alert=alerts.append,
                    default_deadline_ms=100,
                )
                try:
                    with self.assertRaises(TimeoutError) as caught:
                        adapter.execute_snippet(
                            "x", "main", [], timeout_ms=None  # type: ignore[arg-type]
                        )
                finally:
                    adapter.close()

                self.assertIsInstance(caught.exception.__cause__, Timeout)
                alert = alerts[-1]
                self.assertEqual(alert.kind, ErrorKind.TIMEOUT)
                self.assertEqual(alert.op, "sleep")
                self.assertEqual(alert.target, "echo")
                self.assertEqual(alert.phase, "call")

    def test_reconnects_after_transport_failure(self) -> None:
        if os.name == "nt":
            self.skipTest("signal-based kill is POSIX only")
        for host in self.hosts:
            with self.subTest(host=host.name):
                alerts: list[SidecarAlert] = []
                adapter = SidecarSandboxAdapter(
                    host.binary,
                    client_id=f"core-{host.name}",
                    on_alert=alerts.append,
                )
                try:
                    adapter.execute_snippet("x", "main", [])
                    client = adapter._client
                    self.assertIsNotNone(client)
                    os.kill(client.pid, signal.SIGKILL)

                    with self.assertRaises(EmulationFailureError) as caught:
                        adapter.execute_snippet("x", "main", [])
                    self.assertIsInstance(
                        caught.exception.__cause__, ProtocolError
                    )
                    self.assertIsNone(adapter._client)
                    self.assertEqual(alerts[-1].kind, ErrorKind.PROTOCOL)

                    recovered = adapter.execute_snippet("y", "main", [])
                    self.assertEqual(recovered["source"], "y")
                    self.assertIsNotNone(adapter._client)
                finally:
                    adapter.close()

                self.assertEqual(alerts[-1].kind, ErrorKind.PROTOCOL)


if __name__ == "__main__":
    unittest.main()
