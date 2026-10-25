"""Fetches response bodies for matched requests after a turn ends."""

from __future__ import annotations

import base64
from typing import Any, Sequence

from aio_reverse.adapters.web.cdp.cdp_channel import CdpChannel
from aio_reverse.application.ports.browser_session_port import TurnCapture
from aio_reverse.domain.errors import BrowserSessionError

MAX_BODY_BYTES = 4 * 1024 * 1024


def collect_bodies(
    channel: CdpChannel,
    capture: TurnCapture,
    patterns: Sequence[str],
) -> None:
    """Fetch response bodies for finished requests matching ``patterns``."""

    if not patterns:
        return

    for record in capture.requests:
        url = record.get("url")
        if not url or not any(pattern in url for pattern in patterns):
            continue
        if record.get("finished_at") is None or record.get("error_text"):
            continue

        try:
            body = channel.send(
                "Network.getResponseBody", {"requestId": record["id"]}
            )
        except BrowserSessionError as error:
            record["body_error"] = str(error)
            continue

        text = body.get("body")
        if not isinstance(text, str):
            record["body_error"] = "getResponseBody returned no body string"
            continue

        encoded = body.get("base64Encoded") is True
        try:
            size = (
                len(base64.b64decode(text, validate=True))
                if encoded
                else len(text.encode("utf-8"))
            )
        except (ValueError, TypeError) as error:
            record["body_error"] = f"invalid base64 body: {error}"
            continue

        if size > MAX_BODY_BYTES:
            record["body_error"] = (
                f"body is {size} bytes, above the {MAX_BODY_BYTES} byte cap"
            )
            continue

        record["body"] = text
        record["body_encoding"] = "base64" if encoded else "utf-8"
        record["body_bytes"] = size

    channel.ensure_usable()
