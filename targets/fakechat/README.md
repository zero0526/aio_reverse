# fakechat

Target cục bộ dùng cho kiểm chứng E2E (Phase 8). Trang được phục vụ bởi
`tests/fixtures/fake_chat_server.py` tại `http://127.0.0.1:8765/`.

- HTML có textarea, nút send, nút stop, nút new chat và message assistant.
- Mỗi lượt gọi `fetch('/backend-api/conversation')`, mở
  `EventSource('/backend-api/stream')` (3 message) và `WebSocket('/ws')` (2 frame).
- Không chứa dữ liệu thật, không gọi dịch vụ bên ngoài.

Chạy:

```bash
uv run python tests/fixtures/fake_chat_server.py --port 8765
uv run aio-reverse web login fakechat
uv run aio-reverse web run fakechat --script send_prompt --script send_prompt \
  --var prompt="ping"
```
