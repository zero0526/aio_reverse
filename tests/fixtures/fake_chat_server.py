"""Local fake chat page for end-to-end checks (HTTP, SSE and WebSocket)."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

PAGE = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>Fake Chat</title></head>
<body>
<button data-testid="create-new-chat-button">New chat</button>
<div id="messages"></div>
<textarea id="prompt-textarea"></textarea>
<button data-testid="send-button">Send</button>
<script>
(function () {
  var turn = 0;
  var messages = document.getElementById('messages');
  var input = document.getElementById('prompt-textarea');
  var send = document.querySelector('[data-testid="send-button"]');
  var newChat = document.querySelector('[data-testid="create-new-chat-button"]');

  function stopButton() {
    return document.querySelector('[data-testid="stop-button"]');
  }
  function showStop() {
    if (stopButton()) { return; }
    var button = document.createElement('button');
    button.setAttribute('data-testid', 'stop-button');
    button.textContent = 'Stop';
    document.body.appendChild(button);
  }
  function hideStop() {
    var button = stopButton();
    if (button) { button.remove(); }
  }
  function addReply(text) {
    var node = document.createElement('div');
    node.setAttribute('data-message-author-role', 'assistant');
    node.textContent = text;
    messages.appendChild(node);
  }

  newChat.addEventListener('click', function () {
    messages.replaceChildren();
    input.value = '';
  });

  send.addEventListener('click', async function () {
    var prompt = input.value;
    if (!prompt) { return; }
    turn += 1;
    var current = turn;
    input.value = '';
    showStop();

    void navigator.userAgent;
    void navigator.webdriver;
    void document.body.getBoundingClientRect();

    try {
      var response = await fetch('/backend-api/conversation?turn=' + current, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prompt: prompt})
      });
      await response.json();
    } catch (error) {
      hideStop();
      throw error;
    }

    var pending = 2;
    var settled = false;
    function finish() {
      if (settled) { return; }
      pending -= 1;
      if (pending > 0) { return; }
      settled = true;
      addReply('reply ' + current + ' to ' + prompt);
      hideStop();
    }

    var stream = new EventSource('/backend-api/stream?turn=' + current);
    var sseCount = 0;
    stream.addEventListener('message', function () {
      sseCount += 1;
      if (sseCount === 3) { stream.close(); finish(); }
    });
    stream.addEventListener('error', function () {
      if (stream.readyState === EventSource.CLOSED) { stream.close(); finish(); }
    });

    var socket = new WebSocket('ws://' + location.host + '/ws?turn=' + current);
    var frames = 0;
    socket.addEventListener('message', function () {
      frames += 1;
      if (frames === 2) { socket.close(); finish(); }
    });
    socket.addEventListener('error', function () { finish(); });
  });
})();
</script>
</body>
</html>
"""


class FakeChatHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "FakeChat/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._html()
        elif parsed.path == "/backend-api/stream":
            self._sse(self._turn(parsed.query))
        elif parsed.path == "/ws" and self.headers.get("Upgrade") == "websocket":
            self._websocket(self._turn(parsed.query))
        else:
            self.send_error(404, "unknown path")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/backend-api/conversation":
            self.send_error(404, "unknown path")
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        time.sleep(0.1)
        self._json({"ok": True, "echo": body.decode("utf-8", "replace")})

    def log_message(self, format: str, *args: object) -> None:
        return

    @staticmethod
    def _turn(query: str) -> str:
        values = parse_qs(query).get("turn")
        return values[0] if values else "0"

    def _html(self) -> None:
        payload = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, turn: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for index in range(1, 4):
            self.wfile.write(
                f"data: turn {turn} message {index}\n\n".encode("utf-8")
            )
            self.wfile.flush()
            time.sleep(0.05)
        self.close_connection = True

    def _websocket(self, turn: str) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(400, "missing Sec-WebSocket-Key")
            return
        accept = base64.b64encode(
            hashlib.sha1(f"{key}{WS_GUID}".encode("ascii")).digest()
        ).decode("ascii")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        for index in (1, 2):
            self._frame(f'{{"turn":"{turn}","frame":{index}}}')
            time.sleep(0.05)
        self._frame(b"", opcode=0x8)
        self.close_connection = True

    def _frame(self, payload: str | bytes, opcode: int = 0x1) -> None:
        data = payload.encode("utf-8") if isinstance(payload, str) else payload
        length = len(data)
        if length < 126:
            header = bytes([0x80 | opcode, length])
        elif length < 65536:
            header = bytes([0x80 | opcode, 126]) + length.to_bytes(2, "big")
        else:
            header = bytes([0x80 | opcode, 127]) + length.to_bytes(8, "big")
        self.wfile.write(header + data)
        self.wfile.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), FakeChatHandler)
    print(f"fake chat listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
