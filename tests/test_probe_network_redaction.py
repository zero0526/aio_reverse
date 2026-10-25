"""Tests for applying the artifact body policy to probe network records."""

from __future__ import annotations

import unittest
from typing import Any

from aio_reverse.application.probe_network_redaction import redact_probe_network


class ProbeNetworkRedactionTest(unittest.TestCase):
    def probe(self, network: list[Any]) -> dict[str, Any]:
        return {"network": network}

    def test_redacts_body_when_url_is_not_allowed(self) -> None:
        probe = self.probe(
            [{"url": "https://example.test/api", "body": '{"prompt":"hi"}'}]
        )

        result = redact_probe_network(probe, ())

        entry = result["network"][0]
        self.assertIsNone(entry["body"])
        self.assertTrue(entry["body_redacted"])

    def test_keeps_body_when_url_matches(self) -> None:
        probe = self.probe(
            [
                {
                    "url": "https://example.test/backend-api/x",
                    "body": '{"prompt":"hi"}',
                }
            ]
        )

        result = redact_probe_network(probe, ("/backend-api/",))

        entry = result["network"][0]
        self.assertEqual(entry["body"], '{"prompt":"hi"}')
        self.assertNotIn("body_redacted", entry)

    def test_leaves_records_without_body_untouched(self) -> None:
        probe = self.probe([{"url": "https://example.test/api"}])

        result = redact_probe_network(probe, ())

        self.assertNotIn("body_redacted", result["network"][0])

    def test_rejects_missing_network_list(self) -> None:
        with self.assertRaises(ValueError):
            redact_probe_network({}, ())

    def test_rejects_non_object_entry(self) -> None:
        with self.assertRaises(ValueError):
            redact_probe_network(self.probe(["nope"]), ())

    def test_rejects_body_without_url(self) -> None:
        with self.assertRaises(ValueError):
            redact_probe_network(self.probe([{"body": "x"}]), ())

    def test_rejects_non_string_body(self) -> None:
        with self.assertRaises(ValueError):
            redact_probe_network(
                self.probe([{"url": "https://example.test/", "body": {}}]),
                (),
            )


if __name__ == "__main__":
    unittest.main()
