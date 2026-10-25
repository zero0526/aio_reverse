# ChatGPT — Bài học chuyển giao

> Các bài học dưới đây rút từ run `20261025T115909Z-chatgpt` và các lần sửa lỗi cùng
> ngày. Mỗi bài học gồm bằng chứng và quy tắc áp dụng cho target khác.

## 1. Readiness là một phần tử render, không phải `readyState`

**Bằng chứng:** sau restart Chrome, trang kẹt `readyState=interactive`, chưa có composer;
`ready_expression` timeout. Reload một lần thì pass, không cần login lại.

**Quy tắc:** `ready_expression` phải kiểm tra chính control sẽ dùng, có kích thước render.
Không dùng `readyState` hoặc một landmark chỉ có trong DOM.

## 2. Visibility là một phần của identity

**Bằng chứng:** "New chat" để lại heading assistant cũ trong workspace ẩn. Count thô = 3,
count render = 0. Click toàn trang có thể rơi vào bản ẩn.

**Quy tắc:** mọi count/wait/click phải render-aware; selector phải nằm trong container hẹp
(`form`, `[data-composer-placement]`). Ghi cả raw và rendered khi lập DOM map.

## 3. Count delta, không count tuyệt đối

**Bằng chứng:** turn đầu có `replies_before=0`; nếu hard-code 0, turn hai sẽ pass ngay vì
hội thoại đã có phản hồi cũ.

**Quy tắc:** luôn `count` trước hành động, `save`, rồi `wait_count > saved`. Không dùng
`> 0` trừ khi mission chắc chắn bắt đầu từ trang trắng.

## 4. Trusted input cần focus + trusted click

**Bằng chứng:** composer là ProseMirror contenteditable; `Input.insertText` sau click
trusted hoạt động. Gọi JS set value/click sẽ tạo `isTrusted=false`.

**Quy tắc:** dùng `click` + `type` của engine. Không dùng `evaluate` để set value, click,
hoặc submit.

## 5. Chờ tín hiệu hoàn tất của chính ứng dụng

**Bằng chứng:** khi stream xong, `button[aria-label="Stop"]` biến mất; sau đó network
quiet 2 s. `wait_count` một mình có thể pass khi phản hồi mới bắt đầu render nhưng chưa
xong.

**Quy tắc:** chờ cả tín hiệu UI (Stop hidden) và tín hiệu transport (network quiet). Không
dùng `sleep` làm cơ chế chờ chính.

## 6. `sse=0` không có nghĩa không stream

**Bằng chứng:** `probe.sse=0`, nhưng POST `f/conversation` via `fetch`, status 200,
`body_bytes=null`; có WebSocket realtime. Phản hồi stream bằng fetch/ReadableStream.

**Quy tắc:** phân loại transport bằng ba lớp: probe.network, POST stream, WebSocket. Không
kết luận từ một con số.

## 7. Artifact chứa dữ liệu nhạy cảm

**Bằng chứng:** `network.json` có header, request body, response body cho URL khớp
`network_patterns`; `sse.json`/`websocket.json` có payload.

**Quy tắc:** chỉ trích path/method/status/body_bytes. Không dán artifact vào báo cáo,
không commit `data/output/`. Chọn `network_patterns` hẹp vì nó bật body capture.

## 8. Probe là session-scoped; inject lại sau navigation

**Bằng chứng:** `InteractiveSession` cài probe bằng init script + evaluate, verify
`window.__WRE.drain`; `navigate` cài lại. Thiếu probe → `ProbeUnavailableError`.

**Quy tắc:** không giả định `__WRE` tồn tại sau navigate/CSP change. Nếu thiếu, gọi
`web inject_probe` và kiểm tra init script/CSP.

## 9. Cold start hydration là một state

**Bằng chứng:** sau restart Chrome, trang chưa hydrate; một reload có kiểm soát giải
quyết. Không thêm auto-reload để tránh che lỗi auth/UI.

**Quy tắc:** ghi nhận caveat, chờ `ready_expression`; nếu cần reload, làm một lần có log,
không đưa vào chain đo mà không nêu rõ.

## 10. Env capture phải xử lý thenable

**Bằng chứng:** getter `ReadableStreamDefaultReader.closed` trả promise; capture gọi mà
không gắn rejection handler → 13 unhandled rejection. Sửa bằng handler rỗng trước encode;
run sau 0 exception.

**Quy tắc:** khi gọi getter trong snapshot, coi kết quả có thể là thenable; gắn handler
trước khi encode. Kiểm tra `exceptions.json` sau mỗi run.

## 11. Telemetry là nhiễu có chủ đích

**Bằng chứng:** `/ces/v1/rgstr` lặp lại, có 202; `wait_network_quiet` nhìn mọi event
`Network.*`.

**Quy tắc:** loại telemetry khỏi `network_patterns`; nếu quiet không đạt, dùng tín hiệu UI
hoặc tăng `ms` có kiểm soát; không chặn telemetry bằng JS.

## 12. Báo cáo trước, code sau

**Bằng chứng:** lần đầu dùng selector cũ `#prompt-textarea` làm login timeout; nếu không
lập DOM map và state matrix, lỗi sẽ lặp lại. Sau khi mô tả state machine + transport +
chain, việc sửa target/script rõ ràng và kiểm chứng được.

**Quy tắc:** không viết code tích hợp khi báo cáo còn thiếu mục; mọi thay đổi chain phải
kèm artifact chứng minh.
