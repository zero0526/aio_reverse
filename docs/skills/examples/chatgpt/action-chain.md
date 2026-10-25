# ChatGPT — Action chain

> Đi kèm [`behavior-report.md`](behavior-report.md). Target: `targets/chatgpt/`.

## 1. Sơ đồ

```text
open()
  └─ start Chrome (profile bền) → attach CDP → ready_expression → login_expression
       └─ inject probe (__WRE)

setup: new_chat
  click New chat
    → wait_hidden assistant (render)
      → wait_visible home composer
        → trạng thái: ready_home (assistant render = 0)

turn: send_prompt
  count assistant → replies_before
    → type {{prompt}} vào composer
      → click Send
        → wait_count assistant > replies_before
          → wait_hidden Stop
            → wait_network_quiet 2000 ms
              → settled_thread
```

## 2. Setup — `new_chat.json`

```json
{
  "name": "new_chat",
  "description": "Open a fresh conversation before the measured turns",
  "timeout_s": 60,
  "actions": [
    {
      "type": "click",
      "selector": "button[aria-label=\"New chat\"]"
    },
    {
      "type": "wait_hidden",
      "selector": "h4[data-conversation-role=\"assistant\"]",
      "timeout_s": 30
    },
    {
      "type": "wait_visible",
      "selector": "form[data-chatgpt-composer][data-composer-placement=\"home\"] div.ProseMirror[contenteditable=\"true\"]",
      "timeout_s": 30
    }
  ]
}
```

Vì sao:

- `click` chọn match render đầu tiên; "New chat" nằm ngoài composer nên selector toàn
  trang là đủ và ổn định.
- `wait_hidden` assistant dùng nghĩa "không còn match render", nên bỏ qua DOM cũ bị ẩn.
- `wait_visible` kiểm tra đúng composer home, không chấp nhận composer thread còn sót.

Setup không ghi artifact. Nó chạy một lần trước các turn.

## 3. Turn — `send_prompt.json`

```json
{
  "name": "send_prompt",
  "description": "Type one prompt, send it and wait for the streamed reply to settle",
  "timeout_s": 240,
  "actions": [
    {
      "type": "count",
      "selector": "h4[data-conversation-role=\"assistant\"]",
      "save": "replies_before"
    },
    {
      "type": "type",
      "selector": "form[data-chatgpt-composer] div.ProseMirror[contenteditable=\"true\"]",
      "text": "{{prompt}}"
    },
    {
      "type": "click",
      "selector": "form[data-chatgpt-composer] button[aria-label=\"Send\"]"
    },
    {
      "type": "wait_count",
      "selector": "h4[data-conversation-role=\"assistant\"]",
      "greater_than": "{{replies_before}}",
      "timeout_s": 240
    },
    {
      "type": "wait_hidden",
      "selector": "button[aria-label=\"Stop\"]",
      "timeout_s": 240
    },
    {
      "type": "wait_network_quiet",
      "ms": 2000,
      "timeout_s": 30
    }
  ]
}
```

## 4. Vì sao từng bước

| Bước | Vì sao | Nếu bỏ |
|---|---|---|
| `count` trước | Trang có thể đã có phản hồi cũ | `wait_count > 0` pass ngay, không chờ phản hồi mới |
| `type` | Tự click focus rồi `Input.insertText` | Gõ vào chỗ khác hoặc không vào ProseMirror |
| `click` Send | Trusted mouse event tại tâm nút | Gọi JS click → `isTrusted=false`, có thể bị bỏ qua |
| `wait_count > before` | Xác nhận phản hồi mới đã render | Kết thúc trước khi có phản hồi |
| `wait_hidden` Stop | Tín hiệu UI trực tiếp của stream | Kết thúc giữa stream |
| `wait_network_quiet` | Chốt chunk cuối/telemetry | Artifact thiếu dữ liệu cuối |

## 5. Số đo thực tế

Run `20261025T115909Z-chatgpt`:

| Bước | Thời lượng |
|---|---|
| count | ~0.002 s |
| type | ~5.04 s |
| click Send | ~1.20 s |
| wait_count | ~38.15 s |
| wait_hidden Stop | ~2.77 s |
| wait_network_quiet | ~2.00 s |
| Toàn turn | ~49.23 s |

`type` mất ~5 s do click/focus và phản ứng SPA. Không đặt timeout 5 s.

`wait_count` ~38 s là thời gian stream thực tế; timeout 240 s cho biên an toàn.

## 6. Biến

- `prompt` do người chạy truyền: `--var prompt="ping"`.
- `replies_before` do `count` lưu trong cùng script.
- Không có biến nào được truyền tự động giữa hai turn khác nhau.

## 7. Chạy

```bash
uv run aio-reverse web login chatgpt
uv run aio-reverse web run chatgpt --script send_prompt --var prompt="ping"
```

Nhiều lượt trong một run:

```bash
uv run aio-reverse web run chatgpt \
  --script send_prompt --var prompt="first" \
  --script send_prompt --var prompt="second"
```

Lưu ý: `--var` áp dụng cho mọi script; nếu cần giá trị khác nhau, chạy hai lần hoặc tạo
script riêng. Biến `replies_before` được tính lại ở mỗi turn.

## 8. Phương án thay thế (chưa xác nhận)

- Gửi bằng `web press Enter` sau khi focus composer. Chưa dùng trong chain đo vì chưa
  kiểm chứng hành vi submit của ProseMirror với Enter trên tài khoản này.
- Bỏ `wait_network_quiet` nếu telemetry nền làm quiet không đạt; khi đó dựa vào Stop
  hidden + `wait_count`, và ghi rõ giảm độ chắc chắn.
- Bỏ `wait_hidden` assistant trong setup nếu chắc chắn route mới đã render; hiện giữ để
  chống route cache.

## 9. Tín hiệu lỗi

| Lỗi | Nơi nổi lên | Ý nghĩa |
|---|---|---|
| `click target not found or not rendered` | `click` | Selector sai hoặc toàn bộ bản khớp bị ẩn |
| `did not hold within ...` | `wait_*` | Trạng thái không đạt trong timeout |
| `count ... returned ...` | `count` | Expression trả không phải số nguyên |
| `network did not stay quiet` | `wait_network_quiet` | Telemetry/polling nền |
| `ActionScriptError` | Engine | Lỗi có script, step index, type, message |
| `AuthenticationRequiredError` | `open()` | Phiên hết hạn; login tay lại |

## 10. Khi nào phải sửa chain

- Raw/rendered của selector đổi.
- Có thêm placement/route composer.
- Stop không còn là tín hiệu kết thúc.
- Stream chuyển sang EventSource/WebSocket.
- Telemetry làm quiet timeout.
- Thời lượng stream vượt timeout.

Mọi thay đổi phải cập nhật [`behavior-report.md`](behavior-report.md) và chạy lại một
turn đo, không chỉ handover.
