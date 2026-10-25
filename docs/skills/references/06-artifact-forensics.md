# 06 — Đọc artifact và kiểm chứng

Mục đích: biến artifact thành bằng chứng có thể kiểm tra, không biến nó thành nguồn rò
dữ liệu.

## 1. Cấu trúc

```text
data/output/web/<target>/<run_id>/
├── run.json
├── summary.json
└── turn-01/
    ├── request.json
    ├── steps.json
    ├── probe.json
    ├── network.json
    ├── sse.json
    ├── websocket.json
    ├── console.json
    ├── exceptions.json
    ├── env.json
    ├── page.json
    └── timings.json
```

`run_id` dạng `<UTC timestamp>-<target>`, ví dụ `20261025T115909Z-chatgpt`.

## 2. Thứ tự đọc

1. `run.json` — trạng thái run, script, biến, lỗi (nếu có).
2. `summary.json` — tổng hợp theo turn và toàn run.
3. `turn-NN/steps.json` — từng bước, thời lượng, giá trị `save`.
4. `turn-NN/page.json` — URL/title/readyState cuối turn.
5. `turn-NN/network.json` — request/response metadata.
6. `turn-NN/probe.json` — reads/calls/events/network/sse/websocket.
7. `turn-NN/sse.json`, `websocket.json` — chỉ khi cần xác nhận transport/payload.
8. `turn-NN/exceptions.json`, `console.json` — lỗi runtime.
9. `turn-NN/env.json` — môi trường quan sát tại thời điểm cuối turn.
10. `turn-NN/timings.json` — tương quan thời gian.

## 3. `run.json`

Các trường chính:

```text
run_id, target, entry_url, port
setup_scripts, turn_scripts, variables
started_at, finished_at, status
turns[] (bản tóm tắt từng turn)
error (chỉ khi status = failed)
```

`status` là `running`, `completed`, hoặc `failed`. Khi failed, run vẫn được ghi để giữ
bằng chứng; lỗi gốc được re-raise cho CLI/MCP.

## 4. `summary.json`

```text
run_id, target, entry_url, patterns
setup_scripts, setup_steps
turns[]:
  index, script, variables, steps, duration_s
  requests, matched_requests[] (method, url, status, body_bytes)
  sse_events, ws_frames, console_errors, exceptions
  probe: reads/calls/events/network/sse/websocket + top_reads/top_calls
totals: tổng của các turn
```

Dùng `summary.json` để trả lời nhanh:

- Bao nhiêu request, bao nhiêu khớp pattern?
- Có exception/console error không?
- Probe có ghi nhận đủ reads/calls/network/stream không?
- Turn có đúng script và biến không?

## 5. `steps.json`

Mỗi phần tử:

```json
{
  "index": 0,
  "type": "count",
  "started_at": 1792929554.9005823,
  "ended_at": 1792929554.902848,
  "saved": "replies_before",
  "value": 0
}
```

Kiểm tra:

- Số bước khớp số action trong script.
- Thứ tự type khớp thiết kế.
- `value` của `count`/`evaluate` hợp lý.
- Không có bước nào kéo dài bất thường mà không có lý do.

## 6. `probe.json` và drain

- `drain_probe()` gọi `window.__WRE.drain()`, trả snapshot rồi **clear** bộ đếm.
- Vì vậy mỗi `turn-NN/probe.json` chỉ chứa dữ liệu của turn đó.
- `probe.network[].body` là **sample tối đa ~200 ký tự** do probe ghi. Trước khi ghi
  artifact, Python thay sample bằng `null` + `body_redacted: true` nếu URL không khớp
  `body_capture_patterns`; chỉ URL được phép mới giữ sample.
- Nếu probe không có sau navigation, `drain_probe` fail loud với `ProbeUnavailableError`.
- `probe.installed` cho biết probe đã cài; `startedAt`/`elapsed` cho biết cửa sổ đo.

Kiểm tra cách ly giữa các turn:

```bash
# Hai turn liên tiếp trong cùng run
python3 - <<'PY'
import json
from pathlib import Path
run = Path('data/output/web/<target>/<run_id>')
for turn in sorted(run.glob('turn-*')):
    probe = json.loads((turn/'probe.json').read_text())
    print(turn.name, {k: len(probe.get(k, [])) for k in ('reads','calls','events','network','sse','websocket')})
PY
```

Nếu turn 2 lặp dữ liệu turn 1, nghi ngờ drain không chạy hoặc chỉ số turn bị lẫn.

## 7. `network.json`

- `started_at`, `ended_at`: cửa sổ capture của turn.
- `requests[]`: một record mỗi request, có thể `orphan` nếu bắt đầu trước turn.
- `request_body_bytes`/`request_body_sha256`: metadata của body gửi đi; `null` nếu
  request không có body.
- `request_body` (raw) chỉ có khi URL khớp `body_capture_patterns`.
- Response `body` chỉ có khi URL khớp `body_capture_patterns` và lấy được.
- `body_bytes` là kích thước response body; `null` thường gặp với stream hoặc request
  chưa xong.

**Cảnh báo dữ liệu:** header nhạy cảm (`cookie`, `set-cookie`, `authorization`,
`proxy-authorization`) đã bị thay bằng `[redacted]`, nhưng file vẫn có
`request_headers`, `response_headers`, và có thể có `request_body`/`body`. Không mở
công khai, không dán vào chat, không commit. Khi cần trích, chỉ lấy
method/path/status/body_bytes.

## 8. `sse.json` và `websocket.json`

- `sse.json`: `request_id`, `event_name`, `event_id`, `data_bytes`, `data_sha256`,
  `timestamp`. Raw `data` chỉ có khi target bật `stream_payloads: true`.
- `websocket.json`: `request_id`, `direction`, `opcode`, `payload_bytes`,
  `payload_sha256`, `timestamp`. Raw `payload` chỉ có khi bật `stream_payloads`.
- `probe.json` cũng chỉ có metadata SSE/WS; hai lớp bằng chứng giờ nhất quán về mặc
  định.

Quy tắc: chỉ đọc raw `data`/`payload` khi thật cần xác nhận schema, và không ghi giá
trị vào báo cáo. Ưu tiên `*_bytes`/`*_sha256` và `probe.websocket` để lấy
frames/bytes/state.

## 9. `exceptions.json` và `console.json`

- Exception thường là tín hiệu mạnh: unhandled rejection, lỗi hydration, lỗi quyền.
- Console error có thể do extension hoặc third-party; đọc `type` và stack.
- Không bỏ qua exception chỉ vì run vẫn `completed`. Ghi nhận và giải thích.

Ví dụ đã gặp: getter trả promise bị gọi trong env capture tạo unhandled rejection; đã sửa
bằng cách gắn rejection handler. Nếu gặp lại, kiểm tra `env.json`/`exceptions.json` và
phiên bản `wre`.

## 10. `env.json` và `page.json`

- `page.json`: `url`, `title`, `ready_state` tại cuối turn.
- `env.json`: snapshot môi trường (`window`, `navigator`, `screen`, `location`,
  `history`, `performance`, `crypto`, `Intl`), độ sâu theo `env_depth`.
- Env snapshot có thể chứa thông tin fingerprint; không dán toàn bộ vào docs.

## 11. Kiểm tra tính nhất quán

| Kiểm tra | Kỳ vọng |
|---|---|
| Số bước | Bằng số action trong script |
| `steps[].index` | 0..N-1, không trùng |
| `requests` | >= `matched_requests` |
| `probe` lists | Có đủ 6 khóa; list rỗng hợp lệ |
| `sse_events` | Khớp số event CDP (nếu có) |
| `ws_frames` | Khớp số frame CDP (nếu có) |
| `sse_events[].data` / `ws_frames[].payload` | Vắng mặt nếu `stream_payloads=false`; khớp `*_sha256` nếu bật |
| Header nhạy cảm | `[redacted]` ở mọi map header |
| `request_body`/`body` | Chỉ có khi URL khớp `body_capture_patterns` |
| `console_errors` | Đếm type `error`/`assert` |
| `exceptions` | 0 nếu không có lỗi runtime |
| `page.ready_state` | `complete` sau khi ổn định |
| `run.status` | `completed` |

Bất kỳ lệch nào phải được giải thích trong báo cáo, không bỏ qua.

## 12. Run thất bại

Khi fail:

- `run.json` có `status: "failed"` và `error`.
- `summary.json` có thể không tồn tại.
- `turn-NN/` có thể thiếu hoặc thiếu file nếu lỗi xảy ra trước khi ghi.
- `session.close(keep_browser=True)` vẫn chạy trong `finally`.

Quy trình: đọc `run.json` → xác định bước lỗi từ `steps` (nếu có) → chạy lại handover
đúng bước → sửa target/script → chạy lại. Không xóa run thất bại; nó là bằng chứng.

## 13. Checklist cổng 6

- [ ] `run.status = completed`.
- [ ] Số bước khớp thiết kế.
- [ ] `exceptions = 0`, `console_errors = 0` hoặc đã giải thích.
- [ ] `page.ready_state = complete`, URL đúng.
- [ ] `probe` có đủ khóa và số liệu hợp lý.
- [ ] `network` có request hành động + hydrate.
- [ ] `sse`/`websocket` khớp transport đã xác định.
- [ ] Không có dữ liệu nhạy cảm bị trích vào báo cáo.
- [ ] Nếu nhiều turn: dữ liệu mỗi turn độc lập.
