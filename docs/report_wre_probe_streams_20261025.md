# Báo cáo nghiệm thu — Phase 1: Rust probe SSE/WebSocket + `drain()`

Ngày: 2026-10-25

## 1. Mục tiêu task

Bổ sung hook Server-Sent Events và WebSocket vào probe runtime của Rust, thêm `drain()` để tách dữ liệu theo từng lượt, đồng thời mở rộng `SurfaceSpec`/`ProbeDump` để bật/tắt và đọc dữ liệu stream.

## 2. Đã làm được gì (chi tiết thay đổi)

- `SurfaceSpec` có thêm `sse` và `websocket` (mặc định `true`, deserialize `default_true`), được đưa vào `Default`, `merge()` và `config()` gửi xuống runtime.
- `ProbeDump` có thêm `sse` và `websocket`, `parse()` đọc hai mảng này từ dump JSON.
- Runtime giữ native `EventTarget.prototype.addEventListener` trước khi bị trap, để các hook stream vẫn hoạt động sau khi `trapEvents` thay thế listener.
- Hook `EventSource`: ghi `url`, `state`, `messages`, `bytes`, `lastBytes`, `errors`, `site`, mốc thời gian; bọc `close()` để đánh dấu stream đã đóng. Không ghi nội dung payload.
- Hook `WebSocket`: ghi `url`, `protocols`, `framesOut`/`bytesOut`, `framesIn`/`bytesIn`, `errors`, `closeCode`, `closeReason`, `site`; bọc `send()` trên instance và lắng nghe `open/message/close/error`.
- Cả hai shim dùng `disguise()`: `toString()` vẫn trả về native source, `name` và static constants (`CONNECTING/OPEN/CLOSING/CLOSED`) được giữ.
- Tách `snapshot()`; `dump()` không xóa dữ liệu; `drain()` trả snapshot rồi reset counter; stream còn mở được giữ lại với counter 0, stream đã đóng bị loại sau lượt kế tiếp; `reset()` xóa cả stream.
- Test: 5 unit test trong `lib.rs` và 10 test V8 trong `runs_in_v8.rs`, gồm fake `EventSource`/`WebSocket` có emitter, kiểm tra metadata, stealth và vòng đời drain/reset.

## 3. Làm tại đâu (file & vị trí)

| File | Nội dung |
|---|---|
| `libs/web-re-toolkit/crates/wre-probe/src/lib.rs` | `SurfaceSpec` fields `sse`/`websocket`; `default_true`; `merge()`; `config()`; `ProbeDump` fields + `parse()`; test config và parse stream |
| `libs/web-re-toolkit/crates/wre-probe/src/runtime.rs` | `nativeAdd`; `sse`/`sockets` state; `dataLength`, `copyRecord`, `copyStatics`, `resetStream`; `trapEventSource`, `trapWebSocket`; `snapshot`, `clearTurn`; API `dump/drain/reset` |
| `libs/web-re-toolkit/crates/wre-probe/tests/runs_in_v8.rs` | Fake DOM có listener emitter; test `records_sse_and_websocket_metadata`, `drain_resets_open_streams_and_forgets_closed_ones`, `stream_wrappers_still_report_as_native` |

## 4. Hướng dẫn và kết quả verify

Lệnh:

```bash
cd libs/web-re-toolkit
cargo test -p wre-probe
```

Kết quả thực tế:

```text
running 5 tests (src/lib.rs)
test result: ok. 5 passed; 0 failed

running 10 tests (tests/runs_in_v8.rs)
test result: ok. 10 passed; 0 failed
```

Tổng: 15 test pass, 0 fail.
