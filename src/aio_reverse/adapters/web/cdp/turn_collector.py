"""Accumulates CDP network, runtime and stream events for one turn."""

from __future__ import annotations

import copy
import threading
import time
from typing import Any, Sequence

from aio_reverse.adapters.web.cdp.cdp_values import (
    call_frames,
    header_map,
    initiator_type,
    initiator_url,
    optional_bool,
    optional_number,
    optional_str,
    remote_value,
    required_str,
)
from aio_reverse.application.ports.browser_session_port import TurnCapture
from aio_reverse.domain.content_fingerprint import text_metadata
from aio_reverse.domain.errors import BrowserSessionError


class TurnCollector:
    """Accumulates CDP events between ``begin`` and ``snapshot``."""

    def __init__(
        self,
        body_capture_patterns: Sequence[str] = (),
        stream_payloads: bool = False,
    ) -> None:
        self._lock = threading.Lock()
        self._body_capture_patterns = tuple(body_capture_patterns)
        self._stream_payloads = stream_payloads
        self._requests: dict[str, dict[str, Any]] = {}
        self._extra_request_headers: dict[str, dict[str, str]] = {}
        self._extra_response_headers: dict[str, dict[str, str]] = {}
        self._console: list[dict[str, Any]] = []
        self._exceptions: list[dict[str, Any]] = []
        self._sse_events: list[dict[str, Any]] = []
        self._ws_frames: list[dict[str, Any]] = []
        self._started_at = 0.0
        self._last_network = 0.0

    def begin(self) -> None:
        with self._lock:
            self._requests = {}
            self._extra_request_headers = {}
            self._extra_response_headers = {}
            self._console = []
            self._exceptions = []
            self._sse_events = []
            self._ws_frames = []
            self._started_at = time.time()
            self._last_network = time.monotonic()

    def last_network_activity(self) -> float:
        with self._lock:
            return self._last_network

    def absorb(self, event: dict[str, Any]) -> None:
        method = event["method"]
        params = event["params"]
        with self._lock:
            if method.startswith("Network."):
                self._last_network = time.monotonic()

            if method == "Network.requestWillBeSent":
                self._request_started(params)
            elif method == "Network.requestWillBeSentExtraInfo":
                self._headers_extra(
                    params, method, self._extra_request_headers
                )
            elif method == "Network.responseReceived":
                self._response(params)
            elif method == "Network.responseReceivedExtraInfo":
                self._headers_extra(
                    params, method, self._extra_response_headers
                )
            elif method == "Network.loadingFinished":
                self._loading_finished(params)
            elif method == "Network.loadingFailed":
                self._loading_failed(params)
            elif method == "Network.eventSourceMessageReceived":
                self._sse_event(params)
            elif method == "Network.webSocketFrameSent":
                self._ws_frame(params, "sent")
            elif method == "Network.webSocketFrameReceived":
                self._ws_frame(params, "received")
            elif method == "Runtime.consoleAPICalled":
                self._console_line(params)
            elif method == "Runtime.exceptionThrown":
                self._exception(params)

    def snapshot(self) -> TurnCapture:
        with self._lock:
            requests = []
            for request_id, record in self._requests.items():
                item = copy.deepcopy(record)
                item["request_headers_extra"] = dict(
                    self._extra_request_headers.get(request_id, {})
                )
                item["response_headers_extra"] = dict(
                    self._extra_response_headers.get(request_id, {})
                )
                requests.append(item)

            return TurnCapture(
                requests=requests,
                console=list(self._console),
                exceptions=list(self._exceptions),
                sse_events=list(self._sse_events),
                ws_frames=list(self._ws_frames),
                started_at=self._started_at,
                ended_at=time.time(),
            )

    def _request_started(self, params: dict[str, Any]) -> None:
        method = "Network.requestWillBeSent"
        request_id = required_str(params, "requestId", method)
        request = params.get("request")
        if not isinstance(request, dict):
            raise BrowserSessionError(f"{method} has no request object")

        url = required_str(request, "url", method)
        post_data = optional_str(request, "postData")
        if post_data is None:
            request_body = None
            request_body_bytes = None
            request_body_sha256 = None
        else:
            request_body_bytes, request_body_sha256 = text_metadata(post_data)
            request_body = (
                post_data if self._captures_body(url) else None
            )

        record: dict[str, Any] = {
            "id": request_id,
            "url": url,
            "method": required_str(request, "method", method),
            "resource_type": optional_str(params, "type"),
            "request_headers": header_map(request.get("headers"), method),
            "request_body": request_body,
            "request_body_bytes": request_body_bytes,
            "request_body_sha256": request_body_sha256,
            "initiator": initiator_type(params),
            "initiator_url": initiator_url(params),
            "timestamp": optional_number(params, "timestamp", method),
            "wall_time": optional_number(params, "wallTime", method),
            "status": None,
            "status_text": None,
            "response_headers": {},
            "mime_type": None,
            "protocol": None,
            "remote_address": None,
            "from_disk_cache": None,
            "from_service_worker": None,
            "encoded_data_length": None,
            "finished_at": None,
            "error_text": None,
            "canceled": None,
            "redirect_chain": [],
            "orphan": False,
        }

        existing = self._requests.get(request_id)
        if existing is not None:
            record["redirect_chain"] = list(existing.get("redirect_chain", []))
            record["redirect_chain"].append(
                {
                    "url": existing.get("url"),
                    "status": existing.get("status"),
                    "timestamp": existing.get("timestamp"),
                }
            )

        self._requests[request_id] = record
        self._extra_response_headers.pop(request_id, None)

    def _response(self, params: dict[str, Any]) -> None:
        method = "Network.responseReceived"
        request_id = required_str(params, "requestId", method)
        response = params.get("response")
        if not isinstance(response, dict):
            raise BrowserSessionError(f"{method} has no response object")

        record = self._record_for(request_id)
        record["url"] = optional_str(response, "url") or record["url"]
        record["status"] = optional_number(response, "status", method)
        record["status_text"] = optional_str(response, "statusText")
        record["response_headers"] = header_map(
            response.get("headers"), method
        )
        record["mime_type"] = optional_str(response, "mimeType")
        record["protocol"] = optional_str(response, "protocol")
        record["remote_address"] = optional_str(response, "remoteIPAddress")
        record["from_disk_cache"] = optional_bool(response, "fromDiskCache")
        record["from_service_worker"] = optional_bool(
            response, "fromServiceWorker"
        )
        if record["resource_type"] is None:
            record["resource_type"] = optional_str(params, "type")

    def _headers_extra(
        self,
        params: dict[str, Any],
        method: str,
        store: dict[str, dict[str, str]],
    ) -> None:
        request_id = required_str(params, "requestId", method)
        headers = header_map(params.get("headers"), method)
        store.setdefault(request_id, {}).update(headers)

    def _loading_finished(self, params: dict[str, Any]) -> None:
        method = "Network.loadingFinished"
        request_id = required_str(params, "requestId", method)
        record = self._record_for(request_id)
        record["finished_at"] = optional_number(params, "timestamp", method)
        record["encoded_data_length"] = optional_number(
            params, "encodedDataLength", method
        )

    def _loading_failed(self, params: dict[str, Any]) -> None:
        method = "Network.loadingFailed"
        request_id = required_str(params, "requestId", method)
        record = self._record_for(request_id)
        record["error_text"] = required_str(params, "errorText", method)
        record["canceled"] = optional_bool(params, "canceled")
        record["finished_at"] = optional_number(params, "timestamp", method)

    def _sse_event(self, params: dict[str, Any]) -> None:
        method = "Network.eventSourceMessageReceived"
        data = required_str(params, "data", method)
        data_bytes, data_sha256 = text_metadata(data)
        entry: dict[str, Any] = {
            "request_id": required_str(params, "requestId", method),
            "event_name": optional_str(params, "eventName"),
            "event_id": optional_str(params, "eventId"),
            "data_bytes": data_bytes,
            "data_sha256": data_sha256,
            "timestamp": optional_number(params, "timestamp", method),
        }
        if self._stream_payloads:
            entry["data"] = data
        self._sse_events.append(entry)

    def _ws_frame(self, params: dict[str, Any], direction: str) -> None:
        method = f"Network.webSocketFrame{direction.title()}"
        frame = params.get("response")
        if not isinstance(frame, dict):
            raise BrowserSessionError(f"{method} has no frame object")
        payload = required_str(frame, "payloadData", method)
        payload_bytes, payload_sha256 = text_metadata(payload)
        entry: dict[str, Any] = {
            "request_id": required_str(params, "requestId", method),
            "direction": direction,
            "opcode": optional_number(frame, "opcode", method),
            "payload_bytes": payload_bytes,
            "payload_sha256": payload_sha256,
            "timestamp": optional_number(params, "timestamp", method),
        }
        if self._stream_payloads:
            entry["payload"] = payload
        self._ws_frames.append(entry)

    def _captures_body(self, url: str | None) -> bool:
        return isinstance(url, str) and any(
            pattern in url for pattern in self._body_capture_patterns
        )

    def _console_line(self, params: dict[str, Any]) -> None:
        method = "Runtime.consoleAPICalled"
        kind = required_str(params, "type", method)
        args = params.get("args")
        if not isinstance(args, list):
            raise BrowserSessionError(f"{method} has no args list")
        self._console.append(
            {
                "type": kind,
                "args": [remote_value(value, method) for value in args],
                "stack": call_frames(params.get("stack"), method),
                "timestamp": optional_number(params, "timestamp", method),
            }
        )

    def _exception(self, params: dict[str, Any]) -> None:
        method = "Runtime.exceptionThrown"
        details = params.get("exceptionDetails")
        if not isinstance(details, dict):
            raise BrowserSessionError(f"{method} has no exceptionDetails")
        exception = details.get("exception")
        self._exceptions.append(
            {
                "text": optional_str(details, "text"),
                "url": optional_str(details, "url"),
                "line": optional_number(details, "lineNumber", method),
                "column": optional_number(details, "columnNumber", method),
                "exception": (
                    remote_value(exception, method)
                    if isinstance(exception, dict)
                    else None
                ),
                "stack": call_frames(details.get("stack"), method),
                "timestamp": optional_number(params, "timestamp", method),
            }
        )

    def _record_for(self, request_id: str) -> dict[str, Any]:
        record = self._requests.get(request_id)
        if record is not None:
            return record
        # The request may have started before begin(); keep the evidence rather
        # than dropping its response events.
        record = {
            "id": request_id,
            "url": None,
            "method": None,
            "resource_type": None,
            "request_headers": {},
            "request_body": None,
            "request_body_bytes": None,
            "request_body_sha256": None,
            "initiator": None,
            "initiator_url": None,
            "timestamp": None,
            "wall_time": None,
            "status": None,
            "status_text": None,
            "response_headers": {},
            "mime_type": None,
            "protocol": None,
            "remote_address": None,
            "from_disk_cache": None,
            "from_service_worker": None,
            "encoded_data_length": None,
            "finished_at": None,
            "error_text": None,
            "canceled": None,
            "redirect_chain": [],
            "orphan": True,
        }
        self._requests[request_id] = record
        return record
