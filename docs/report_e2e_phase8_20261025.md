# Report — Phase 8: kiểm chứng E2E (2026-10-25)

> Cập nhật cùng ngày: phần ChatGPT thật đã hoàn tất sau báo cáo này; xem
> `docs/report_chatgpt_e2e_20261025.md`. Báo cáo dưới đây giữ nguyên kết quả
> fakechat/MCP tại thời điểm chạy.

## 1. Mục tiêu

Kiểm chứng kiến trúc mới trên môi trường thật:

- Probe Rust emit từ target ChatGPT phải là JavaScript hợp lệ.
- Trang chat giả có HTTP, SSE và WebSocket phải chạy được qua `web login` + `web run`
  2 lượt, artifact đầy đủ.
- Lượt 2 chỉ chứa dữ liệu lượt 2 để chứng minh `window.__WRE.drain()` reset đúng.
- MCP server stdio phải chạy được chuỗi `web_open → web_run_script → web_state → web_close`.
- Ghi lại phần chưa chạy được (ChatGPT thật) thay vì báo pass sai.

## 2. Thay đổi

### 2.1 Fixture chat giả

- Thêm `tests/fixtures/fake_chat_server.py`: HTTP server stdlib, phục vụ:
  - `/` — HTML có textarea, send, stop, new chat và message assistant;
  - `POST /backend-api/conversation` — trả JSON sau 100 ms;
  - `GET /backend-api/stream` — SSE 3 message rồi đóng;
  - `GET /ws` — WebSocket handshake thủ công, gửi 2 frame rồi close.
- Server không gọi dịch vụ ngoài, không chứa dữ liệu thật.

### 2.2 Target fakechat

- `targets/fakechat/target.json`: trỏ `127.0.0.1:8765`, Chrome port 9565, probe
  `fingerprint`, bật SSE/WebSocket.
- `targets/fakechat/scripts/new_chat.json` và `send_prompt.json`: cùng cấu trúc action
  script với ChatGPT, timeout ngắn hơn cho test.
- `targets/fakechat/README.md`: ghi rõ đây là target E2E cục bộ.

Không sửa code application/adapters cho Phase 8.

### 2.3 Tài liệu

- `docs/plans.md`: Phase 8 chuyển `một phần`, tick 6/7 mục, thêm nhật ký và sai lệch.
- `docs/capture_analystic.md`: cập nhật trạng thái E2E, kết quả fakechat/MCP và việc còn lại.

## 3. Vị trí file chính

| Nội dung | Vị trí |
|---|---|
| Fixture server | `tests/fixtures/fake_chat_server.py` |
| Target fakechat | `targets/fakechat/target.json` |
| Script fakechat | `targets/fakechat/scripts/*.json` |
| Run artifact | `data/output/web/fakechat/20261025T063735Z-fakechat/` |
| MCP run artifact | `data/output/web/fakechat/20261025T063816Z-fakechat/` |
| Kế hoạch / nhật ký | `docs/plans.md` |
| Kiến trúc / kết quả | `docs/capture_analystic.md` |

## 4. Kiểm chứng

### 4.1 Probe ChatGPT hợp lệ

```bash
uv run aio-reverse web probe chatgpt > /tmp/aio-phase8/probe.js
node --check /tmp/aio-phase8/probe.js
wc -c /tmp/aio-phase8/probe.js
```

Kết quả thực tế:

```text
19494 /tmp/aio-phase8/probe.js
```

`node --check` không in lỗi (exit 0).

### 4.2 Fixture endpoints

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/
curl -s -N --max-time 3 'http://127.0.0.1:8765/backend-api/stream?turn=1'
curl -s -X POST -d '{"prompt":"x"}' \
  'http://127.0.0.1:8765/backend-api/conversation?turn=1'
```

Kết quả thực tế:

```text
200
data: turn 1 message 1
data: turn 1 message 2
data: turn 1 message 3
{"ok": true, "echo": "{\"prompt\":\"x\"}"}
```

### 4.3 Login + 2 lượt đo

```bash
uv run aio-reverse web login fakechat
uv run aio-reverse web run fakechat --script send_prompt --script send_prompt \
  --var prompt="phase8 ping" --json
```

Login trả:

```json
{"target":"fakechat","page":{"url":"http://127.0.0.1:8765/","title":"Fake Chat","ready_state":"complete"}}
```

Run trả (rút gọn):

```text
run_id 20261025T063735Z-fakechat
turns 2
setup_steps 2
turn 1: steps 6, requests 2, sse_events 3, ws_frames 2
        probe reads 2 calls 2 network 1 sse 1 websocket 1
turn 2: steps 6, requests 2, sse_events 3, ws_frames 2
        probe reads 2 calls 2 network 1 sse 1 websocket 1
```

### 4.4 Chứng minh `drain()` theo lượt

Đọc trực tiếp artifact:

```text
turn 1
  probe network urls ['/backend-api/conversation?turn=1']
  probe sse [('/backend-api/stream?turn=1', 3, True)]
  probe ws [('ws://127.0.0.1:8765/ws?turn=1', 2, True)]
  cdp requests [POST conversation?turn=1, GET stream?turn=1]

turn 2
  probe network urls ['/backend-api/conversation?turn=2']
  probe sse [('/backend-api/stream?turn=2', 3, True)]
  probe ws [('ws://127.0.0.1:8765/ws?turn=2', 2, True)]
  cdp requests [POST conversation?turn=2, GET stream?turn=2]
```

Mỗi lượt có đúng 1 network record, 1 SSE record, 1 WebSocket record; reads/calls không
cộng dồn. Lượt 2 không chứa bất kỳ URL `turn=1` nào.

Mỗi turn có đủ 12 file: `request.json`, `steps.json`, `probe.json`, `network.json`,
`sse.json`, `websocket.json`, `console.json`, `exceptions.json`, `env.json`, `page.json`,
`timings.json` (cộng thư mục `turn-NN/`). `env.json` khoảng 351 KB với `env_depth=2`.

### 4.5 MCP stdio smoke

Client thật (`mcp.client.stdio.stdio_client` + `ClientSession`) gọi:

1. `tools/list` → 11 tool:
   `web_click`, `web_close`, `web_evaluate`, `web_inject_probe`, `web_navigate`,
   `web_open`, `web_press`, `web_run_script`, `web_state`, `web_targets`, `web_type`.
2. `web_open(fakechat)` → `http://127.0.0.1:8765/`, title `Fake Chat`.
3. `web_run_script(fakechat, send_prompt, {prompt: "mcp ping"})` →
   run `20261025T063816Z-fakechat`, probe đủ reads/calls/network/sse/websocket.
4. `web_state(fakechat)` → URL và `ready_state=complete`.
5. `web_close(fakechat)` → `{"closed": true, "browser": "kept running"}`.

### 4.6 Regression

```bash
uv run python -m unittest discover -s tests
```

Kết quả thực tế:

```text
Ran 112 tests in 0.301s

OK
```

### 4.7 Chưa chạy: ChatGPT thật

- Chưa có `data/profiles/chatgpt` và không có phiên đăng nhập ChatGPT trong môi trường
  tự động.
- Không tự động hóa credential; cần người dùng chạy:
  `uv run aio-reverse web login chatgpt`, đăng nhập tay, rồi
  `uv run aio-reverse web run chatgpt --script send_prompt --var prompt="ping"`.
- Không đánh dấu pass cho mục này trong `docs/plans.md`.
