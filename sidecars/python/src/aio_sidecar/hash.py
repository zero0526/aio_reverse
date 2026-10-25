"""Protocol v1 schema hashing.

``hello.schema_hash`` is FNV-1a 64-bit over canonical JSON of the engine
descriptor: recursively sorted object keys, compact separators, UTF-8 without
ASCII escaping. FNV-1a keeps every host implementation dependency-free.
"""

from __future__ import annotations

import json
from typing import Any

_FNV_OFFSET_BASIS = 0xCBF29CE484222325
_FNV_PRIME = 0x100000001B3
_MASK_64 = 0xFFFFFFFFFFFFFFFF


def canonical_json(value: Any) -> bytes:
    """Serializes *value* to the canonical JSON byte representation."""
    text = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return text.encode("utf-8")


def fnv1a64(data: bytes) -> str:
    """Returns the FNV-1a 64-bit hash of *data* as 16 lowercase hex digits."""
    digest = _FNV_OFFSET_BASIS
    for byte in data:
        digest ^= byte
        digest = (digest * _FNV_PRIME) & _MASK_64
    return f"{digest:016x}"


def schema_hash(descriptor: Any) -> str:
    """Returns the wire-protocol schema hash for an engine descriptor."""
    return fnv1a64(canonical_json(descriptor))
