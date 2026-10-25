"""Checks that protocol/contract.json agrees with the shared runtime types."""

from __future__ import annotations

import json
import struct
import unittest
from pathlib import Path

from wre_runtime.errors import ErrorKind
from wre_runtime.frames import encode_frame

from aio_sidecar import RETRYABLE_KINDS, fnv1a64, schema_hash
from aio_sidecar.hash import canonical_json

CONTRACT = json.loads(
    (Path(__file__).resolve().parent.parent / "protocol" / "contract.json").read_text(
        encoding="utf-8"
    )
)
FIXTURE = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "echo.descriptor.json").read_text(
        encoding="utf-8"
    )
)

BASE_OPS = [
    "hello",
    "describe",
    "targets",
    "metrics",
    "open",
    "close",
    "health",
    "warmup",
    "shutdown",
    "diag",
]


class ContractTest(unittest.TestCase):
    def test_protocol_and_bundle(self) -> None:
        self.assertEqual(CONTRACT["protocol"], 1)
        self.assertEqual(CONTRACT["bundle"], "aio")
        self.assertEqual(set(CONTRACT["envelopes"]), {"req", "res", "evt", "cancel"})
        self.assertEqual(CONTRACT["base_ops"], BASE_OPS)

    def test_error_kinds_match_runtime_taxonomy(self) -> None:
        self.assertEqual(list(CONTRACT["error_kinds"]), list(ErrorKind.ALL))
        retryable = {
            kind for kind, is_retryable in CONTRACT["error_kinds"].items() if is_retryable
        }
        self.assertEqual(retryable, set(RETRYABLE_KINDS))

    def test_framing_matches_runtime_encoder(self) -> None:
        framing = CONTRACT["framing"]
        self.assertEqual(framing["header_bytes"], 8)
        self.assertEqual(framing["json_length_field_bytes"], 4)
        self.assertEqual(framing["bin_length_field_bytes"], 4)
        self.assertEqual(framing["byte_order"], "big-endian")
        self.assertEqual(framing["max_json_bytes"], 64 * 1024 * 1024)
        self.assertEqual(framing["max_bin_bytes"], 512 * 1024 * 1024)

        envelope = {"t": "req", "v": 1, "id": 1, "op": "hello", "params": {}}
        binary = b"\x00\x01\xff"
        encoded = encode_frame(envelope, binary)
        json_len, bin_len = struct.unpack(">II", encoded[:8])
        self.assertEqual(json_len, len(encoded) - 8 - bin_len)
        self.assertEqual(bin_len, len(binary))

    def test_engine_exception_detail_key(self) -> None:
        self.assertEqual(CONTRACT["engine_exception_detail_key"], "engine_exception")

    def test_schema_hash_is_fnv1a64(self) -> None:
        schema = CONTRACT["schema_hash"]
        self.assertEqual(schema["algorithm"], "fnv1a64")
        self.assertEqual(schema["hex_length"], 16)
        self.assertTrue(schema["canonical_json"])
        self.assertEqual(fnv1a64(b""), "cbf29ce484222325")
        self.assertEqual(fnv1a64(canonical_json({"b": 1, "a": 2})), fnv1a64(b'{"a":2,"b":1}'))
        self.assertRegex(schema_hash(FIXTURE), r"^[0-9a-f]{16}$")


if __name__ == "__main__":
    unittest.main()
