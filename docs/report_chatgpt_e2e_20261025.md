# Báo cáo — E2E ChatGPT thật + sửa primitive theo DOM mới

> Ngày: 2026-10-25. Phạm vi: Phase 8 — kiểm chứng `chatgpt.com` thật và các sửa lỗi phát sinh.
> Không commit. Không ghi cookie, token, request body hay nội dung hội thoại vào tài liệu.

## 1. Mục tiêu

1. Chạy `web login` → `web run` trên tài khoản ChatGPT do người dùng đăng nhập thủ công.
2. Xác nhận profile bền: dừng Chrome rồi mở lại không cần đăng nhập lại.
3. Sửa các lỗi phát hiện trong lần chạy thật:
   - DOM ChatGPT đổi sang composer ProseMirror và nút `aria-label`, selector cũ không còn.
   - ChatGPT giữ DOM route cũ trong workspace `display:none` khiến đếm/click nhầm bản ẩn.
   - Env capture gọi getter trả promise (`ReadableStreamDefaultReader.closed`) gây unhandled rejection.

## 2. Thay đổi

### 2.1 DOM mới của ChatGPT

| Mục đích | Selector |
|---|---|
| Composer | `form[data-chatgpt-composer] div.ProseMirror[contenteditable="true"]` |
| Composer trang chủ | `form[data-chatgpt-composer][data-composer-placement="home"]` |
| Send | `form[data-chatgpt-composer] button[aria-label="Send"]` |
| Stop stream | `button[aria-label="Stop"]` |
| New chat | `button[aria-label="New chat"]` |
| Assistant message | `h4[data-conversation-role="assistant"]` |
| Đăng nhập | `button[aria-label="Open profile menu"]` |

`new_chat` chờ tin nhắn assistant cũ biến mất (chỉ xét phần tử render) rồi chờ composer
trang chủ. `send_prompt` đếm assistant hiển thị, gõ, gửi, chờ count tăng, chờ nút Stop
biến mất, rồi chờ network quiet 2000 ms.

### 2.2 Primitive chỉ xét phần tử render

Thêm `src/aio_reverse/application/page_element_expressions.py` làm nguồn duy nhất cho
expression JS:

- `visible_count_expression(selector)`
- `visible_presence_expression(selector)`
- `visible_absence_expression(selector)`
- `first_visible_click_point_expression(selector)`

`expression_waiter.py` dùng các helper này cho `count`/`wait_count`/`wait_visible`/
`wait_hidden`; `chrome_cdp_session.click` chọn match render đầu tiên và fail loud nếu
không có (kèm selector + số match).

### 2.3 Env capture không tạo unhandled rejection

`libs/web-re-toolkit/crates/wre-env/src/capture.rs`: khi getter trả thenable, gắn ngay
handler rejection rỗng trước khi encode. Thêm test
`promise_getters_get_a_rejection_handler` trong `tests/realm.rs`.

## 3. File thay đổi

| File | Thay đổi |
|---|---|
| `src/aio_reverse/application/page_element_expressions.py` | Mới — expression lọc phần tử render |
| `src/aio_reverse/application/expression_waiter.py` | Dùng helper render cho count/wait |
| `src/aio_reverse/adapters/web/cdp/chrome_cdp_session.py` | Click chọn match render đầu tiên |
| `libs/web-re-toolkit/crates/wre-env/src/capture.rs` | Gắn rejection handler cho getter thenable |
| `libs/web-re-toolkit/crates/wre-env/tests/realm.rs` | Test getter trả thenable |
| `tests/test_page_element_expressions.py` | Mới — 3 test expression |
| `tests/test_action_engine.py` | Fake session cập nhật theo expression mới |
| `tests/test_cdp_routing.py` | Thêm test click tại điểm render |
| `targets/chatgpt/target.json` | Ready/login expression mới |
| `targets/chatgpt/scripts/{new_chat,send_prompt}.json` | Selector + điều kiện chờ mới |
| `targets/chatgpt/README.md` | Bảng selector đã xác nhận + lý do lọc render |
| `docs/plans.md` | Tick Phase 8, log + sai lệch |
| `docs/capture_analystic.md` | Trạng thái, E2E thật, bài học, checklist |

## 4. Lệnh verify và kết quả thực tế

### 4.1 Unit tests

```bash
uv run python -m unittest discover -s tests
```

Kết quả:

```text
Ran 116 tests in 0.299s

OK
```

Rust:

```bash
cd libs/web-re-toolkit
cargo test -p wre-env
```

```text
running 4 tests ... test result: ok. 4 passed
running 8 tests ... test result: ok. 8 passed
```

Build binary:

```bash
cargo build --release -p wre-cli
```

```text
Finished `release` profile [optimized] target(s) in 12.60s
```

(Ghi nhận warning dead-code có sẵn ở `crates/wre-cli/src/sandbox_cmd.rs` — ngoài phạm vi sửa.)

### 4.2 Login + run thật

```bash
uv run aio-reverse web login chatgpt
```

```json
{
  "target": "chatgpt",
  "page": {"url": "https://chatgpt.com/", "title": "ChatGPT", "ready_state": "complete"}
}
```

Run đầu (trước khi sửa env capture):

```bash
uv run aio-reverse web run chatgpt --script send_prompt --var prompt="ping"
```

```text
run 20261025T115728Z-chatgpt
turns 1 setup_steps 3 steps 6
requests 18 matched 16 sse 0 ws 4 console_errors 0 exceptions 13
probe reads 18 calls 11 events 82 network 12 sse 0 websocket 0
```

13 exception là `TypeError: Failed to read the 'closed' property from
'ReadableStreamDefaultReader': Illegal invocation`, phát sinh từ env capture — đã sửa.

Run cuối (sau khi sửa + rebuild):

```bash
uv run aio-reverse web run chatgpt --script send_prompt --var prompt="ping"
```

```text
run 20261025T115909Z-chatgpt
turns 1 setup_steps 3 steps 6
requests 26 matched 17 sse 0 ws 7 console_errors 0 exceptions 0
probe reads 18 calls 11 events 82 network 17 sse 0 websocket 1
```

Kiểm tra artifact `data/output/web/chatgpt/20261025T115909Z-chatgpt/`:

- `turn-01/steps.json`: 6/6 step thành công; `count` trả `replies_before=0`.
- `turn-01/probe.json`: reads 18, calls 11, events 82, network 17, websocket 1, sse 0.
- `turn-01/exceptions.json`: 0; `console.json`: 0.
- `turn-01/websocket.json`: 7 frame từ CDP; probe ghi 1 WSS mới với frames in/out
  (metadata, không payload).
- `page.json`: hội thoại mới, `ready_state=complete`.
- `sse=0` là đúng cho ChatGPT hiện tại: trang stream bằng `fetch`, không dùng
  `EventSource`. Hook SSE đã được chứng minh bằng fakechat.

### 4.3 Profile bền

```bash
./libs/web-re-toolkit/target/release/wre browser --port 9445 --stop
uv run aio-reverse web state chatgpt
```

Kết quả: `web state` trả page + env snapshot, không yêu cầu đăng nhập lại.

Ghi nhận: lần mở nguội đầu tiên sau restart, trang kẹt `readyState=interactive`
(hydration chưa xong) và `ready_expression` timeout 60 s. Reload trang một lần rồi chạy
`web state` lại thì pass. Không thêm auto-reload để tránh che lỗi auth/UI thật.

## 5. Việc chưa làm

- Phase B marker sweep (ngoài phạm vi).
- Không commit; mọi thay đổi đang ở working tree.
- Chưa thêm retry/reload tự động cho cold start SPA.
