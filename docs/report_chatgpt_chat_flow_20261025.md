# Phân tích luồng chat ChatGPT (ca thực nghiệm chính)

> Ngày: 2026-10-25
> Target: `targets/chatgpt/`
> Run chính: `20261025T133736Z-chatgpt` (sau policy Phase 10)
> Run đối chiếu: `20261025T132414Z-chatgpt` (trước khi vá probe body)
> Tài khoản: người dùng sở hữu, đăng nhập thủ công. Prompt tổng hợp `ping`.
> Quy ước: **Observed** = có trong artifact; **Inferred** = suy luận có căn cứ;
> **Unknown** = chưa đủ bằng chứng.
> Không có cookie, token, header value, body, prompt thật hay conversation ID trong tài
> liệu này. Conversation ID được thay bằng `{id}`.

## 1. Kết luận ngắn

ChatGPT là SPA dùng client-side routing, giữ DOM của route cũ trong workspace ẩn.
Một lượt chat đi qua 5 pha:

```text
home/bootstrap
  → compose (ProseMirror + trusted input)
  → submit
  → prepare + sentinel (chuẩn bị/integrity)
  → POST /backend-api/f/conversation (phản hồi chính, fetch stream)
  → hydrate thread + background (conversations, ads, telemetry)
```

Không dùng `EventSource` (`probe.sse=0`, `sse.json=[]`). Phản hồi chính đi qua
`fetch` + `ReadableStream`; WebSocket `ws.chatgpt.com` là kênh song song, mục đích
**Unknown**. Tín hiệu "xong" đáng tin là **`button[aria-label="Stop"]` biến mất** +
**network quiet**, không phải `readyState`, `body_bytes`, hay `sleep`.

## 2. Bằng chứng

| Chỉ số | Run 18 request (warm) | Run 50 request (cold hơn) |
|---|---|---|
| Status | `completed` | `completed` |
| Steps | 6/6 | 6/6 |
| Request CDP | 18 | 50 |
| Fetch | 14 | 21 |
| Asset (CDN/static) | 4 | 29 |
| SSE events | 0 | 0 |
| WS frame CDP | 2 | 2 |
| Probe network | 12 | 21 |
| Probe websocket | 3 kết nối | 3 kết nối |
| Exception / console error | 0 / 0 | 0 / 0 |
| Raw body/stream trong artifact | 0 | 0 (sau vá probe) |

Số request thay đổi mạnh giữa hai run vì cache/CDN/bootstrap. **Không phân loại pha
theo tổng số request.**

## 3. Mô hình pha

### 3.1 Bootstrap / home

**Observed (run 50 request):**

| Endpoint | Method | Vai trò (Inferred) |
|---|---|---|
| `/backend-api/me` | GET | Danh tính phiên |
| `/backend-api/models` | GET | Danh sách model cho picker |
| `/backend-api/settings/is_adult` | GET | Cờ cài đặt |
| `/backend-api/wham/usage` | GET | Hạn mức/gói |
| `/backend-api/user_segments` | GET | Phân khúc/feature flag |
| `/backend-api/accounts/check/...` | GET | Kiểm tra tài khoản/gói |
| `/backend-api/ps/plugins/installed` | GET | Plugin/connector đã cài |
| `/backend-api/aip/workspace/connector-recommendation` | GET | Gợi ý connector |
| `/backend-api/system_hints` | GET | Gợi ý UI/tính năng |
| `/backend-api/prompt_library/` | GET | Gợi ý prompt ở home |
| `/backend-api/conversations?...` | GET | Sidebar lịch sử |
| `/ces/...` | POST | Telemetry nền |

Các endpoint này xuất hiện trước hoặc xen trong lượt, không phải hệ quả trực tiếp của
việc bấm Send. Nhiều request là `orphan: true` (bắt đầu trước `begin_turn`), nên method
có thể `null`; không suy ra method từ `null`.

### 3.2 Compose

**Observed:** composer là ProseMirror `contenteditable`, không phải textarea.

| Landmark | Selector |
|---|---|
| Form | `form[data-chatgpt-composer]` |
| Vùng nhập | `div.ProseMirror[contenteditable="true"]` |
| Home | `form[data-chatgpt-composer][data-composer-placement="home"]` |
| Thread | `form[data-chatgpt-composer][data-composer-placement="thread"]` |
| Send | `form[data-chatgpt-composer] button[aria-label="Send"]` |
| Stop | `button[aria-label="Stop"]` |

`Input.insertText` chèn toàn bộ text; click Send là trusted mouse event. Trong run 18
request, bước `type` mất ~5.05 s và click Send ~5.24 s dù lệnh CDP đơn lẻ — SPA bận
hydrate/stream. **Không đặt timeout 5 s cho các bước này.**

### 3.3 Submit + prepare + sentinel

Thứ tự Observed trong run 18 request (timestamp tương đối):

```text
prepare        36656.6 → 36657.7   POST /backend-api/f/conversation/prepare
f/conversation 36661.6 → 36670.6   POST /backend-api/f/conversation      ← hành động chính
sentinel/prep  36661.7 → 36664.4   POST /backend-api/sentinel/chat-requirements/prepare
init           36661.9 → 36672.5   POST /backend-api/conversation/init
sentinel/fin   36664.4 → 36673.2   POST /backend-api/sentinel/chat-requirements/finalize
hydrate        36669.6 → 36673.8   GET  /backend-api/conversations/{id}?num_turns=...
```

Ba request `f/conversation`, `sentinel/prepare`, `init` gần như đồng thời; `finalize`
và hydrate chồng lên giai đoạn cuối. Vì vậy **không suy ra thứ tự nhân quả chỉ từ thời
điểm bắt đầu**; cần đối chiếu `steps.json` + UI signal.

**Inferred:**

- `f/conversation/prepare` chuẩn bị ngữ cảnh/lượt trước khi gửi.
- `sentinel/chat-requirements/{prepare,finalize}` là chuỗi integrity; chỉ ghi nhận,
  không replay/không vượt.
- `f/conversation` là hành động chính, trả phản hồi stream.
- `conversation/init` khởi tạo client hội thoại; method Observed là POST trong run này,
  nhưng run cũ từng thấy record `orphan` với method `null`. Không kết luận method cố
  định.
- `f/conversation/prepare` xuất hiện 2 lần; lần thứ hai có thể là preflight cho lượt
  kế/route mới. **Unknown**.

### 3.4 Hydrate + background

| Endpoint | Method | Vai trò (Inferred) |
|---|---|---|
| `/backend-api/conversations/{id}?num_turns=...` | GET | Hydrate thread sau stream |
| `/backend-api/bazaar/conversation/{id}/ads` | GET | Quảng cáo/khuyến nghị trong thread |
| `/backend-api/conversations?...` | GET | Refresh sidebar |
| `/ces/v1/telemetry/intake` | POST | Telemetry |
| `/ces/statsc/flush` | POST | Telemetry flush |

Telemetry và ads có thể chạy sau khi UI đã "xong", nên `wait_network_quiet` cần đủ
`ms` hoặc dùng tín hiệu UI làm chính.

## 4. Transport

| Kênh | Bằng chứng | Kết luận |
|---|---|---|
| EventSource | `probe.sse=0`, `sse.json=[]` | Không dùng |
| fetch | `probe.network` toàn bộ `via=fetch` | Có dùng |
| fetch stream | UI có assistant node trước khi Stop biến mất; POST `f/conversation` mở ~9 s | Phản hồi chính stream qua fetch |
| WebSocket | 3 kết nối `wss://ws.chatgpt.com/...`; một kết nối `framesIn=2`, `bytesIn=414`, `framesOut=0` | Kênh realtime song song; mục đích Unknown |

**Quan trọng:** từ Phase 10, response body không được fetch nếu URL không khớp
`body_capture_patterns`. Vì vậy `body_bytes=null` **không còn là bằng chứng stream**.
Muốn dùng body làm bằng chứng, phải chạy một target/run riêng có pattern hẹp và xóa
artifact sau khi trích.

## 5. Tín hiệu hoàn tất

Run 18 request:

| Bước | Thời lượng Observed |
|---|---|
| `count` assistant | 0.019 s |
| `type` + focus | 5.048 s |
| `click` Send | 5.241 s |
| `wait_count` assistant tăng | 6.356 s |
| `wait_hidden` Stop | 1.428 s |
| `wait_network_quiet` 2 s | 8.011 s |
| Toàn turn | 26.161 s |

`wait_network_quiet` dài hơn 2 s vì còn request nền/telemetry. Thứ tự đúng:

```text
click Send
  → wait_count(assistant > before)     # phản hồi mới đã render
  → wait_hidden(Stop)                  # UI báo stream xong
  → wait_network_quiet(ms=2000)        # chốt network ổn định
```

Không dùng `sleep` cố định; không dùng `count` tuyệt đối (phải dùng delta).

## 6. Flake quan sát

Lần chạy lại `new_chat` fail ở `wait_hidden` assistant sau 30 s: click
`button[aria-label="New chat"]` không điều hướng, trang vẫn ở `/c/{id}`. Click thủ công
bằng CLI cùng selector thành công; chạy lại thì pass.

**Inferred:** click rơi vào overlay/route chưa sẵn sàng, hoặc SPA bỏ qua click trong
lúc hydrate.

Đề xuất (chưa sửa code):

- Trước click New chat, thêm `wait_visible` cho chính nút New chat.
- Sau click, giữ `wait_hidden` assistant + `wait_visible` home composer như hiện tại.
- Nếu vẫn flake, dùng `web navigate chatgpt https://chatgpt.com/` cho setup (đổi lại
  mất state SPA, chậm hơn) hoặc bổ sung retry click có kiểm soát ở tầng action engine.

## 7. Hệ quả cho target/skill

| Hạng mục | Kết luận |
|---|---|
| `network_patterns` | Giữ `/backend-api/`, `/conversation`, `/sentinel/` — chỉ để lọc summary |
| `body_capture_patterns` | Để rỗng cho run thường; chỉ mở hẹp khi cần schema, rồi xóa artifact |
| `stream_payloads` | `false`; WebSocket metadata đủ để nhận diện kênh |
| `setup_scripts` | `new_chat`: click New chat → wait assistant hidden → wait home composer |
| `turn_scripts` | `send_prompt`: count → type → click Send → wait_count → wait_hidden Stop → network quiet |
| Tín hiệu xong | Stop hidden + network quiet; không dùng `body_bytes` |
| Nhiễu | `/ces/*`, ads, sidebar, prompt library, bootstrap |

## 8. Điều chưa biết

- WebSocket `ws.chatgpt.com` mang event gì (presence, conversation update, telemetry?).
- Vì sao `f/conversation/prepare` xuất hiện hai lần trong cùng lượt.
- Hành vi khi stream lỗi giữa chừng (retry, Regenerate, lỗi mạng).
- Khác biệt A/B variant về selector/composer.
- Giới hạn rate limit thực tế của tài khoản.
- Method cố định của `conversation/init` (POST hay GET) giữa các phiên.

Không suy đoán các mục này; cần run riêng có mission rõ ràng.

## 9. Ghi chú an toàn

- Chỉ tài khoản do người dùng sở hữu, đăng nhập tay; không tự động credential.
- Không bypass CAPTCHA/anti-bot/rate limit; chỉ quan sát.
- Không dán body/header/token/prompt/conversation ID vào tài liệu.
- Artifact nằm dưới `data/output/` (gitignored); run mới đã không còn raw body/stream.
- Các run trước Phase 10 còn response body cũ; không dùng làm nguồn trích dẫn mới.

## 10. Lệnh tái lập

```bash
uv run aio-reverse web login chatgpt
uv run aio-reverse web run chatgpt --script send_prompt --var prompt=ping --json
uv run aio-reverse web state chatgpt
```

Kiểm tra policy trên run mới:

```bash
python3 - <<'PY'
import json
from pathlib import Path
run = Path('data/output/web/chatgpt/<run_id>/turn-01')
net = json.loads((run/'network.json').read_text())
probe = json.loads((run/'probe.json').read_text())
print('raw bodies', sum(1 for r in net['requests'] if r.get('request_body') or 'body' in r))
print('raw probe bodies', sum(1 for e in probe['network'] if e.get('body')))
print('redacted probe bodies', sum(1 for e in probe['network'] if e.get('body_redacted')))
PY
```
