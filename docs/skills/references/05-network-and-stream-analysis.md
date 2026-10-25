# 05 — Phân tích network và stream

Mục đích: xác định request nào là bootstrap, request nào là hành động, phản hồi đi bằng
transport nào, và tín hiệu nào chứng minh luồng đã kết thúc — chỉ dùng metadata.

## 1. Ba lớp bằng chứng

| Lớp | File | Phạm vi | Độ nhạy cảm |
|---|---|---|---|
| CDP Network | `turn-NN/network.json` | Mọi request trang phát ra | **Cao**: headers (đã redact), request body metadata, response body theo `body_capture_patterns` |
| Rust probe | `turn-NN/probe.json` | `fetch`/XHR/beacon, reads, calls, events, SSE/WS metadata | Trung bình: URL, site, tên API |
| CDP stream | `turn-NN/sse.json`, `turn-NN/websocket.json` | Từng message/frame | **Cao**: metadata mặc định; raw `data`/`payload` chỉ khi `stream_payloads: true` |

Quy tắc: **không dán nguyên file artifact vào báo cáo**. Trích path, method, status,
body_bytes, thứ tự. Không trích header, body, payload.

## 2. CDP Network ghi gì

Mỗi request có thể có:

```text
id, url, method, resource_type, initiator, initiator_url
request_headers, request_headers_extra
request_body, request_body_bytes, request_body_sha256
status, status_text, response_headers, response_headers_extra
mime_type, protocol, remote_address
timestamp, wall_time, finished_at
encoded_data_length, body_bytes, body_encoding
from_disk_cache, from_service_worker
redirect_chain, canceled, error_text, orphan
```

Bốn điểm phải nhớ:

1. **`network_patterns` chỉ là bộ lọc báo cáo** (`summary.json`, `matched_requests`).
   Nó không còn quyết định việc lưu body.
2. **Response body chỉ được lấy cho URL khớp `body_capture_patterns`** (mặc định rỗng),
   tối đa 4 MB mỗi response, lưu trong `body` (utf-8 hoặc base64).
3. **Request body mặc định chỉ lưu metadata**: `request_body_bytes` + `request_body_sha256`.
   Raw `request_body` chỉ có khi URL khớp `body_capture_patterns`.
4. **Header nhạy cảm luôn bị redact** thành `"[redacted]"`: `cookie`, `set-cookie`,
   `authorization`, `proxy-authorization` (không phân biệt hoa/thường), ở cả header
   thường và `*_extra`. Header phân loại như `content-type`, `mime-type`, `referer`
   vẫn giữ nguyên.

Hệ quả: chọn `body_capture_patterns` hẹp hơn cả `network_patterns`. Không thêm pattern
chỉ để "xem cho đủ". Nếu cần phân tích sâu một endpoint, dùng một run riêng, profile
riêng, và xóa artifact sau khi trích metadata.

`orphan: true` + `method: null` nghĩa là response đến mà request bắt đầu **trước**
`begin_turn`; collector vẫn giữ bằng chứng thay vì bỏ. Không suy ra method từ `null`.

## 3. Rust probe ghi gì

`probe.json` là snapshot từ `window.__WRE.drain()`:

| Khóa | Nội dung |
|---|---|
| `reads` | Thuộc tính bị đọc: `key`, `count`, `first`, `last`, `samples`, `sites` |
| `calls` | Hàm bị gọi: `key`, `count`, `sites`, `results` |
| `events` | Loại event, thời điểm, site |
| `network` | `via` (fetch/xhr/beacon), method, URL, body sample (chỉ khi URL khớp `body_capture_patterns`; ngược lại `null` + `body_redacted`) |
| `sse` | Metadata `EventSource` |
| `websocket` | URL, state, frames in/out, bytes, close code, errors |
| `notes`, `installed`, `startedAt`, `elapsed` | Trạng thái probe |

Probe SSE/WS chỉ ghi **metadata**, không ghi payload. CDP cũng mặc định chỉ ghi
metadata (`data_bytes`/`data_sha256`, `payload_bytes`/`payload_sha256`). Raw
`data`/`payload` chỉ xuất hiện khi target bật `stream_payloads: true` — chỉ nên bật
trong run chuyên biệt và xóa artifact sau khi trích.

## 4. Phân loại transport

```text
Có EventSource?
├─ Có  → probe.sse có phần tử; CDP sse.json có eventSourceMessageReceived
└─ Không
   ├─ Có WebSocket? → probe.websocket + CDP ws frames
   └─ Không
      └─ POST trả 200, body_bytes null/không có body cuối?
         └─ Có thể là fetch + ReadableStream (streaming qua fetch)
```

`probe.sse == 0` **không** có nghĩa trang không stream. Rất nhiều ứng dụng hiện đại
stream bằng `fetch` + `ReadableStream`, không dùng `EventSource`.

Dấu hiệu nhận biết fetch-stream:

- `probe.network` có `via: "fetch"` cho POST hành động.
- UI cập nhật dần trong khi request còn mở (assistant node xuất hiện trước khi
  `Stop` biến mất).
- `body_bytes` chỉ dùng làm bằng chứng stream khi URL khớp `body_capture_patterns`.
  Với policy mặc định, response body không được fetch nên `body_bytes` luôn `null` —
  `null` một mình **không** chứng minh stream.
- Có thể có WebSocket song song cho realtime, nhưng nội dung chính vẫn qua POST stream.

## 5. Suy luận vai trò endpoint

Không dựa vào tên một mình. Kết hợp:

1. **Thứ tự**: bootstrap trước, hành động sau, hydrate sau hành động.
2. **Method**: GET cho đọc, POST cho hành động.
3. **Initiator**: script/page nào phát ra.
4. **Thời điểm**: trước hay sau click.
5. **Tương quan với bước**: `timings.json` + `steps.json`.

Bảng ghi đề xuất:

| Path | Method | Pha | Vai trò suy luận | Bằng chứng |
|---|---|---|---|---|
| `/api/me` | GET | boot | Danh tính phiên | Trước mọi hành động |
| `/api/action/prepare` | POST | trước hành động | Chuẩn bị lượt | Ngay sau click |
| `/api/action` | POST | hành động | Request chính | Body stream |
| `/api/items/{id}` | GET | sau hành động | Hydrate kết quả | Sau POST chính |

Ghi rõ "suy luận" nếu không có tài liệu chính thức.

## 6. Nhiễu telemetry

Trang lớn thường có request nền:

- analytics/telemetry: `/ces/...`, `/rgstr`, `/statsc/flush`, `/collect`, `/beacon`
- feature flags/settings: `/settings`, `/config`, `/user_segments`
- notifications/prefetch: `/notifications`, `/prompt_library`

Cách xử lý:

- Đưa telemetry ra khỏi `network_patterns`.
- Không dùng telemetry để suy ra hành động người dùng.
- Ghi nhận telemetry như một phần hành vi trang, đặc biệt khi nó gây `wait_network_quiet`
  timeout.
- Không chặn telemetry bằng `evaluate`; đó là thay đổi hành vi trang, không phải recon.

## 7. Tín hiệu integrity / anti-automation

Có thể gặp:

- Endpoint `sentinel`/`challenge`/`requirements`.
- Đọc fingerprint: `navigator`, `screen`, `devicePixelRatio`, WebGL, canvas.
- Telemetry dày đặc.
- Token sinh ra từ script, gắn vào header/body.

Skill này **chỉ ghi nhận**, không phân tích để vượt. Báo cáo nên nêu:

- Có tín hiệu hay không.
- Nó xuất hiện ở pha nào.
- Nó có làm chain cần thêm bước chờ không.
- Rủi ro rate limit / phiên bị hạn chế.

Không thử vô hiệu hóa, không replay token, không giả lập fingerprint.

## 8. Cách thu thập

Network/stream chỉ được ghi trong một **turn**:

```bash
uv run aio-reverse web run <target> --script <turn-script> --var name=value
```

`web state`, `web evaluate`, `web click` là one-shot; chúng không tạo `turn-NN/`.
Muốn handover nhiều bước mà vẫn giữ capture, dùng MCP session sống.

Sau run, đọc theo thứ tự:

1. `summary.json` — tổng quan.
2. `steps.json` — hành động và thời điểm.
3. `network.json` — request/response metadata.
4. `probe.json` — ai gọi gì.
5. `sse.json` / `websocket.json` — chỉ khi cần xác nhận transport.
6. `timings.json` — tương quan bước với request.

## 9. Checklist cổng 3

- [ ] Đã phân loại bootstrap / hành động / hydrate / telemetry.
- [ ] Đã xác định transport stream (EventSource, WebSocket, fetch-stream).
- [ ] Đã giải thích `sse=0` nếu có.
- [ ] Đã kiểm tra `websocket` metadata và CDP frames (nếu có).
- [ ] Đã ghi nhận endpoint integrity/anti-automation ở mức quan sát.
- [ ] Đã xác định tín hiệu "xong" của UI và của network.
- [ ] Không có body/header/payload trong báo cáo.
- [ ] `network_patterns` được chọn hẹp; `body_capture_patterns` hẹp hơn hoặc rỗng.
- [ ] Nếu đọc `sse.json`/`websocket.json`, xác nhận `stream_payloads` có được bật
      đúng mục đích không.
