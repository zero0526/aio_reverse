"""Unit tests for ``aio_sidecar`` that do not need a built engine binary."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aio_sidecar import (
    RETRYABLE_KINDS,
    ErrorKind,
    ResourceError,
    SidecarAlert,
    canonical_json,
    connect,
    fnv1a64,
    schema_hash,
)
from aio_sidecar.alerts import emit_alert, utc_now

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "conformance"
    / "fixtures"
    / "echo.descriptor.json"
)


class HashTests(unittest.TestCase):
    def test_fnv1a64_vectors(self) -> None:
        self.assertEqual(fnv1a64(b""), "cbf29ce484222325")
        self.assertEqual(fnv1a64(b"a"), "af63dc4c8601ec8c")
        self.assertEqual(fnv1a64(b"foobar"), "85944171f73967e8")

    def test_canonical_json_sorts_keys_recursively(self) -> None:
        self.assertEqual(
            canonical_json({"b": 1, "a": {"d": 2, "c": 3}}),
            b'{"a":{"c":3,"d":2},"b":1}',
        )

    def test_canonical_json_keeps_utf8(self) -> None:
        self.assertEqual(
            canonical_json({"x": "héllo"}),
            '{"x":"héllo"}'.encode("utf-8"),
        )

    def test_schema_hash_is_order_independent(self) -> None:
        self.assertEqual(
            schema_hash({"a": 1, "b": [1, {"d": 4, "c": 3}]}),
            schema_hash({"b": [1, {"c": 3, "d": 4}], "a": 1}),
        )

    def test_schema_hash_of_fixture_is_16_hex(self) -> None:
        descriptor = json.loads(FIXTURE.read_text(encoding="utf-8"))
        digest = schema_hash(descriptor)
        self.assertRegex(digest, r"^[0-9a-f]{16}$")
        self.assertEqual(digest, schema_hash(descriptor))


class AlertTests(unittest.TestCase):
    def _alert(self) -> SidecarAlert:
        return SidecarAlert(
            kind=ErrorKind.RESOURCE,
            message="boom",
            retryable=True,
            phase="call",
            client_id="c1",
            target="echo",
            op="execute",
            session="s1",
            binary="/opt/echo-engine",
            pid=42,
            detail={"errno": 2},
            exception=ResourceError("boom", retryable=True),
            occurred_at=utc_now(),
        )

    def test_emit_alert_invokes_handler_with_payload(self) -> None:
        seen = []
        alert = self._alert()
        emit_alert(alert, seen.append)
        self.assertEqual(seen, [alert])
        self.assertEqual(alert.phase, "call")
        self.assertTrue(alert.retryable)
        self.assertEqual(alert.target, "echo")
        self.assertEqual(alert.op, "execute")

    def test_emit_alert_logs_when_no_handler(self) -> None:
        with self.assertLogs("aio_sidecar", level="ERROR") as logs:
            emit_alert(self._alert(), None)
        self.assertIn("kind=resource", logs.output[0])
        self.assertIn("boom", logs.output[0])

    def test_failing_handler_does_not_mask_or_raise(self) -> None:
        def handler(_alert: SidecarAlert) -> None:
            raise RuntimeError("handler boom")

        with self.assertLogs("aio_sidecar", level="ERROR"):
            emit_alert(self._alert(), handler)


class ConnectFailureTests(unittest.TestCase):
    def test_missing_binary_alerts_then_raises_resource_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "no-such-engine")
            alerts = []
            with self.assertRaises(ResourceError) as ctx:
                connect(
                    missing,
                    client_id="unit",
                    on_alert=alerts.append,
                    startup_timeout=1.0,
                )

        error = ctx.exception
        self.assertTrue(error.retryable)
        self.assertEqual(error.op, "hello")
        self.assertIsInstance(error.__cause__, FileNotFoundError)

        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert.phase, "connect")
        self.assertEqual(alert.kind, ErrorKind.RESOURCE)
        self.assertEqual(alert.client_id, "unit")
        self.assertEqual(alert.binary, missing)
        self.assertIs(alert.exception, error)
        self.assertIsNone(alert.pid)
        self.assertIsNone(alert.session)


class TaxonomyTests(unittest.TestCase):
    def test_retryable_kinds_match_contract(self) -> None:
        self.assertEqual(
            RETRYABLE_KINDS,
            frozenset(
                {ErrorKind.BLOCKED, ErrorKind.TIMEOUT, ErrorKind.RESOURCE}
            ),
        )


if __name__ == "__main__":
    unittest.main()
