"""Pure content fingerprinting: UTF-8 byte length and SHA-256 of text."""

from __future__ import annotations

import hashlib


def text_metadata(text: str) -> tuple[int, str]:
    """Return the UTF-8 byte length and SHA-256 of one captured text value."""
    data = text.encode("utf-8")
    return len(data), hashlib.sha256(data).hexdigest()
