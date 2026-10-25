# ChatGPT — Network map

> Đi kèm [`behavior-report.md`](behavior-report.md). Run `20261025T115909Z-chatgpt`.
> Chỉ path/method/pha/vai trò. Không query string, ID, header, body.

## 1. Tổng quan

| Chỉ số | Giá trị |
|---|---|
| Tổng request CDP | 26 |
| Khớp `network_patterns` | 17 |
| Probe network | 17 (tất cả `fetch`) |
| SSE events | 0 |
| WebSocket | 1 kết nối; probe frames in/out 2/1; CDP frames 7 |
| Console error | 0 |
| Exception | 0 |

`network_patterns = ["/backend-api/", "/conversation", "/sentinel/"]`. Các pattern này
vừa lọc summary vừa bật response body capture cho URL khớp; giữ hẹp.

## 2. Bảng endpoint

| Path | Method | Pha | Vai trò (Inferred) | Ghi chú |
|---|---|---|---|---|
| `/backend-api/settings/user` | GET | boot/send | Cấu hình người dùng | 9.660 bytes |
| `/backend-api/settings/is_adult` | GET* | boot | Cờ cài đặt | Orphan |
| `/backend-api/conversation/init` | GET* | boot | Khởi tạo client hội thoại | 726 bytes |
| `/backend-api/me` | GET* | boot | Danh tính phiên | 375 bytes |
| `/backend-api/accounts/check/v4-2023-04-27` | GET* | boot | Kiểm tra tài khoản/gói | 10.559 bytes |
| `/backend-api/system_hints` | GET* | boot | Gợi ý UI | 2.278 bytes |
| `/backend-api/prompt_library/` | GET | boot | Thư viện prompt | Có query |
| `/backend-api/amphora/clear_settings_cache` | POST | boot | Xóa cache cài đặt | 21 bytes |
| `/backend-api/amphora/notifications` | GET | boot | Thông báo | 35 bytes |
| `/backend-api/user_segments` | GET | sau gửi | Phân khúc người dùng | |
| `/backend-api/f/conversation/prepare` | POST | trước gửi | Chuẩn bị lượt | 384 bytes lần đầu |
| `/backend-api/sentinel/chat-requirements/prepare` | POST | trước gửi | Chuẩn bị challenge | 96.779 bytes |
| `/backend-api/sentinel/chat-requirements/finalize` | POST | trước gửi | Hoàn tất challenge | 2.978 bytes |
| `/backend-api/f/conversation` | POST | hành động | Gửi lượt; stream | `body_bytes=null` |
| `/backend-api/conversations/{id}` | GET | sau gửi | Hydrate hội thoại | |
| `/ces/v1/rgstr` | POST | nền | Telemetry | Lặp 4 lần; 200/202 |
| `/ces/statsc/flush` | POST | nền | Telemetry flush | |
| `wss://ws.chatgpt.com/...` | WebSocket | realtime | Kênh realtime | Mục đích Unknown |

`*` = `orphan: true`, method `null` trong artifact. Không suy ra method.

## 3. Thứ tự quan sát

```text
boot/bootstrap
  settings, is_adult, conversation/init, me, accounts, system_hints,
  prompt_library, amphora/*
        │
        ▼
chuẩn bị lượt
  f/conversation/prepare
  sentinel/.../prepare
  sentinel/.../finalize
        │
        ▼
hành động
  POST f/conversation               ← stream
        │
        ▼
sau hành động
  conversations/{id}                ← hydrate
  user_segments
  f/conversation/prepare (lần 2)    ← Unknown
        │
        ▼
nền
  ces/v1/rgstr (lặp), ces/statsc/flush
```

## 4. Transport

| Kênh | Bằng chứng | Kết luận |
|---|---|---|
| EventSource | `probe.sse=0`, `sse.json=[]` | Không dùng |
| fetch | `probe.network` toàn bộ `via=fetch` | Có dùng |
| fetch-stream | POST `f/conversation` 200, `body_bytes=null` | Phản hồi chính stream |
| WebSocket | `wss://ws.chatgpt.com/...`, 1 kết nối | Realtime song song |

`body_bytes=null` cho POST chính là dấu hiệu stream/chunked hoặc body không lấy được tại
`loadingFinished`; không phải lỗi.

## 5. Nhiễu

- `/ces/*`: telemetry, lặp lại, có 202.
- `/cdn/*`, `persistent.oaistatic.com`: asset tĩnh.
- `/backend-api/prompt_library/`, `system_hints`, `user_segments`, `amphora/*`: phụ trợ.

`wait_network_quiet` nhìn mọi event `Network.*`, nên telemetry nền có thể làm quiet khó
đạt. Run này vẫn đạt quiet 2 s sau khi Stop biến mất.

## 6. Integrity

Chuỗi `sentinel/chat-requirements/{prepare,finalize}` xuất hiện trước POST chính. Đây là
tín hiệu cần ghi nhận, không phải thứ để vượt. Không phân tích/replay token.

## 7. Dữ liệu nhạy cảm

`network.json` có header, request body, và response body cho URL khớp pattern.
`sse.json`/`websocket.json` có payload. Không dán artifact vào báo cáo; chỉ trích
path/method/status/body_bytes.

## 8. Cập nhật Phase 10 (2026-10-25)

Phần 1–7 ở trên mô tả policy trước Phase 10 và được giữ làm lịch sử. Từ Phase 10:

- `network_patterns` chỉ còn lọc summary; body chỉ lấy theo `body_capture_patterns`
  (ChatGPT để rỗng).
- Header nhạy cảm (`cookie`, `set-cookie`, `authorization`, `proxy-authorization`)
  luôn là `[redacted]`.
- Request body chỉ còn `request_body_bytes` + `request_body_sha256`.
- SSE/WS mặc định chỉ metadata; raw chỉ khi `stream_payloads: true` (ChatGPT: false).
- Probe `network[].body` sample cũng bị thay bằng `null` + `body_redacted: true`.

Run mới `20261025T133736Z-chatgpt`: 18 request, 0 raw body/stream, 43 header redacted,
probe 12 entry (7 `body_redacted`), 0 exception. Phân tích pha/transport chi tiết:
[`../../../report_chatgpt_chat_flow_20261025.md`](../../../report_chatgpt_chat_flow_20261025.md).

**Lưu ý:** `body_bytes=null` không còn là bằng chứng stream vì response body không được
fetch theo mặc định.
