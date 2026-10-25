# 04 — Thiết kế action chain

Mục đích: biến hiểu biết về trang thành một chuỗi JSON nhỏ nhất, có tiền điều kiện,
bất biến và tín hiệu hoàn tất rõ ràng.

## 1. Mô hình một script

```text
preconditions
  └─ setup (đưa trang về trạng thái đã biết)
       └─ action 1 → invariant 1
            └─ action 2 → invariant 2
                 └─ ...
                      └─ completion signal
                           └─ cleanup (nếu cần)
```

Script không được "đoán" trạng thái. Mỗi bước hoặc thiết lập trạng thái, hoặc kiểm tra
trạng thái, hoặc thực hiện một hành động với hậu quả quan sát được.

## 2. Mười một action type

| Type | Bắt buộc | Tùy chọn | Hành vi |
|---|---|---|---|
| `navigate` | `url` | `timeout_s` | `Page.navigate`, chờ load |
| `click` | `selector` | `timeout_s` | Click trusted tại tâm match render đầu tiên |
| `type` | `selector`, `text` | `timeout_s` | Click selector để focus, rồi `Input.insertText` |
| `press` | `key` | `timeout_s` | `Enter`, `Escape`, `Tab`, `Backspace` |
| `wait_visible` | `selector` | `timeout_s` | Chờ có ít nhất một match render |
| `wait_hidden` | `selector` | `timeout_s` | Chờ không còn match render |
| `count` | `selector` | `save`, `timeout_s` | Đếm match render, lưu biến |
| `wait_count` | `selector`, `greater_than` | `timeout_s` | Chờ count render > ngưỡng |
| `wait_network_quiet` | `ms` | `timeout_s` | Chờ không có event `Network.*` trong `ms` |
| `sleep` | `ms` | `timeout_s` | Ngủ cố định; chỉ dùng để giãn nhịp, không để chờ UI |
| `evaluate` | `expression` | `save`, `timeout_s` | Chạy JS read-only, trả JSON |

### 2.1 Ngữ nghĩa quan trọng

- `click` chọn **match render đầu tiên**, scroll vào giữa, gửi `mouseMoved`,
  `mousePressed`, `mouseReleased`. Không có match render → lỗi nêu selector và tổng số
  match thô. Không kiểm tra overlay.
- `type` **tự click** vào selector trước khi insert text. Không dùng khi mục tiêu là gõ
  vào element đang focus mà không click.
- `press` chỉ nhận bốn phím. Muốn phím khác phải mở rộng whitelist trong code, không
  nhồi vào `evaluate`.
- `wait_count` so sánh **số match render**, không phải tổng DOM.
- `wait_network_quiet` dựa trên **mọi** event `Network.*`, kể cả telemetry nền. Trang có
  polling sẽ không bao giờ quiet; khi đó dùng tín hiệu UI thay thế.
- `evaluate` chạy với `userGesture: true` và `awaitPromise: true`. Chỉ dùng biểu thức
  read-only; không dùng để sửa DOM.

### 2.2 Timeout

- `timeout_s` của từng action được enforce.
- `timeout_s` cấp script hiện được parse/validate nhưng **chưa được engine enforce**.
  Đây là gap đã ghi nhận; đừng dựa vào nó để chặn một script chạy quá lâu. Đặt timeout
  cho từng action và một ngân sách tổng ở phía người chạy.
- Mặc định action là 30 s nếu không khai báo. Với chờ stream, đặt 120–300 s tùy mục tiêu.

## 3. Template và biến

- Cú pháp: `{{name}}` trong `text`, `url`, `expression`, `greater_than`.
- Biến đến từ `--var name=value` hoặc từ `save` của action trước.
- `count` và `evaluate` có thể `save`.
- Loader giữ template; render tại runtime. Thiếu biến → lỗi nêu tên biến.
- Tên biến phải là identifier: `[A-Za-z_][A-Za-z0-9_]*`.

Ví dụ chuẩn:

```json
{
  "type": "count",
  "selector": "h4[data-conversation-role=\"assistant\"]",
  "save": "replies_before"
}
```

```json
{
  "type": "wait_count",
  "selector": "h4[data-conversation-role=\"assistant\"]",
  "greater_than": "{{replies_before}}",
  "timeout_s": 240
}
```

`greater_than` nhận template và được parse thành số tại runtime.

## 4. Bốn mẫu chain

### Mẫu A — Readiness gate

```json
[
  {"type": "wait_visible", "selector": "<composer>", "timeout_s": 60}
]
```

Dùng ở đầu setup. Không dùng `sleep` thay thế.

### Mẫu B — Submit và chờ kết quả

```json
[
  {"type": "count", "selector": "<assistant>", "save": "before"},
  {"type": "type", "selector": "<composer>", "text": "{{prompt}}"},
  {"type": "click", "selector": "<send>"},
  {"type": "wait_count", "selector": "<assistant>", "greater_than": "{{before}}", "timeout_s": 240},
  {"type": "wait_hidden", "selector": "<stop>", "timeout_s": 240},
  {"type": "wait_network_quiet", "ms": 2000, "timeout_s": 30}
]
```

Vì sao dùng delta count: trang có thể đã có tin nhắn cũ; count tuyệt đối sẽ sai.

### Mẫu C — Điều hướng và reset state

```json
[
  {"type": "click", "selector": "<new-chat>"},
  {"type": "wait_hidden", "selector": "<assistant>", "timeout_s": 30},
  {"type": "wait_visible", "selector": "<home-composer>", "timeout_s": 30}
]
```

Chờ cả "cái cũ biến mất" và "cái mới xuất hiện". Chỉ chờ một phía thường không đủ.

### Mẫu D — Trích xuất dữ liệu

```json
[
  {"type": "evaluate", "expression": "<read-only expression>", "save": "value"}
]
```

Chỉ trích xuất dữ liệu trong phạm vi mission. Không lưu nội dung nhạy cảm vào docs.

## 5. Setup script vs turn script

| Loại | Chạy khi nào | Ghi artifact? | Mục đích |
|---|---|---|---|
| `setup_scripts` | Một lần sau `open()`, trước các turn | Không | Đưa trang về trạng thái đo |
| `turn_scripts` | Mỗi lượt đo | Có, `turn-NN/` | Thực hiện hành động và thu bằng chứng |

Setup phải **idempotent** trong một phiên: chạy lại không làm hỏng trạng thái. Turn
script nên giả định setup đã để lại trạng thái đã biết; không giả định trang mới tinh.

Nhiều `--script` trong một `web run` chạy tuần tự trên cùng session. Mỗi turn có
`begin_turn`/`drain_probe`/`end_turn` riêng. Biến `save` không tự truyền giữa các turn
trừ khi chúng nằm trong cùng một lần gọi script hoặc được truyền qua `--var`.

## 6. Chống mẫu xấu

| Chống mẫu | Vì sao sai | Thay bằng |
|---|---|---|
| `sleep 3000` sau click | Không biết khi nào xong, chậm vô ích | `wait_visible`/`wait_count`/`wait_hidden` |
| `count > 0` tuyệt đối | Trang đã có dữ liệu cũ | Count delta |
| Selector toàn trang | Khớp bản ẩn/route khác | Selector trong container hẹp |
| Reload khi login fail | Che nguyên nhân, có thể mất state | `web login` lại bằng tay |
| `evaluate` để set value/click | Bỏ qua trusted input, dễ sai | `click`/`type` |
| Chờ mỗi nút Send biến mất | Send có thể vẫn hiện | Chờ tín hiệu stream thật (Stop) |
| Bỏ qua `wait_network_quiet` | Stream còn chunk sau khi UI đổi | Chờ quiet hoặc tín hiệu hoàn tất |
| Timeout 5 s cho mọi thứ | SPA chậm, mạng chậm | Timeout theo từng bước |

## 7. Ngân sách thời gian gợi ý

| Bước | Gợi ý |
|---|---|
| `wait_visible` sau navigate | 30–60 s |
| `type` trên SPA nặng | 15–30 s |
| `wait_count` cho phản hồi stream | 120–300 s |
| `wait_hidden` nút Stop | 120–300 s |
| `wait_network_quiet` | `ms=1500–3000`, `timeout_s=30–60` |
| Toàn bộ turn | nhỏ hơn ngân sách mission |

Số đo thực tế phải được ghi vào báo cáo, không chỉ ghi lý thuyết.

## 8. Checklist cổng 4

- [ ] Mỗi bước có tiền điều kiện và bất biến.
- [ ] Không có `sleep` làm cơ chế chờ chính.
- [ ] Count dùng delta, không dùng tuyệt đối.
- [ ] Có tín hiệu hoàn tất của UI **và** tín hiệu network (nếu có stream).
- [ ] Selector nằm trong container hẹp.
- [ ] Timeout từng action hợp lý; biết script-level timeout chưa enforce.
- [ ] Setup idempotent; turn không phụ thuộc thứ tự ngoài ý muốn.
- [ ] Biến `{{...}}` được khai báo hoặc được `save` trước khi dùng.
- [ ] Có kế hoạch chạy lại khi một bước fail (không tự động retry mù).
