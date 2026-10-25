# ChatGPT — Báo cáo hành vi web (ca thực nghiệm)

> Ngày: 2026-10-25
> Target: `targets/chatgpt/`
> Run đo: `20261025T115909Z-chatgpt`
> Phiên bản `wre`: `0.1.0`
> Tài khoản: do người dùng sở hữu, đăng nhập thủ công.
> Quy ước: **Observed** = thấy trong artifact/lệnh; **Inferred** = suy luận có căn cứ;
> **Unknown** = chưa đủ bằng chứng.
> Không có cookie, token, header, body, prompt thật hay ID hội thoại trong tài liệu.

## 0. Tóm tắt một trang

ChatGPT là một ứng dụng SPA có client-side routing và **giữ DOM của route cũ** trong
một workspace bị ẩn. Composer không phải `<textarea>` mà là ProseMirror
`contenteditable`. Một lượt gửi gồm: chuẩn bị lượt (`prepare`), kiểm tra integrity
(`sentinel`), POST hành động chính (`/f/conversation`) trả **stream bằng fetch**, sau đó
hydrate hội thoại và mở một WebSocket realtime. Tín hiệu "xong" đáng tin là **nút Stop
biến mất** cùng **network quiet**, không phải `readyState` hay một `sleep`.

Ba con số định danh run:

```text
requests 26 · matched 17 · sse 0 · ws frames 7 · exceptions 0
probe reads 18 · calls 11 · events 82 · network 17 · websocket 1
steps 6/6 · duration 49.23 s
```

## 1. Mission & phạm vi

| Trường | Giá trị |
|---|---|
| Goal | Gửi một prompt tổng hợp, chờ phản hồi stream kết thúc, thu metadata hành vi |
| Target | `https://chatgpt.com/`, route `/` và `/c/{id}` |
| Account | Tài khoản cá nhân do người dùng đăng nhập tay |
| Allowed | Mở trang, đọc DOM, gõ, gửi, đọc metadata network/probe |
| Forbidden | Đổi cài đặt, mua, xóa hội thoại, tải dữ liệu hàng loạt, vượt anti-bot |
| Evidence | `run.json`, `summary.json`, `turn-01/*.json` |
| Stop | Mất phiên, CAPTCHA/challenge, cảnh báo giới hạn, dữ liệu ngoài phạm vi |

## 2. Bối cảnh & bằng chứng

```text
Chrome port: 9445
Profile:     data/profiles/chatgpt/
Setup:       new_chat
Turn:        send_prompt
Probe:       preset=fingerprint, network/sse/websocket bật
Patterns:    /backend-api/, /conversation, /sentinel/
Run:         data/output/web/chatgpt/20261025T115909Z-chatgpt/
```

Lệnh chính:

```bash
uv run aio-reverse web login chatgpt
uv run aio-reverse web run chatgpt --script send_prompt --var prompt="ping"
uv run aio-reverse web state chatgpt
```

`prompt="ping"` là giá trị tổng hợp dùng cho thực nghiệm, không phải nội dung thật.

## 3. Mô hình trang

### 3.1 SPA shell và route cache

**Observed:** sau khi bấm "New chat", DOM vẫn còn tiêu đề tin nhắn assistant cũ, nhưng
nằm trong một workspace bị ẩn (`display:none`). `querySelectorAll` toàn trang vẫn đếm
được chúng; chỉ khi lọc theo kích thước render mới thấy `0`.

**Inferred:** ứng dụng giữ lại cây DOM của route trước để tái sử dụng, thay vì unmount.
Đây là lý do mọi primitive đếm/click/wait phải **render-aware**.

### 3.2 Composer

**Observed:**

| Thành phần | Selector |
|---|---|
| Form composer | `form[data-chatgpt-composer]` |
| Vùng nhập | `div.ProseMirror[contenteditable="true"]` |
| Composer trang chủ | `form[data-chatgpt-composer][data-composer-placement="home"]` |
| Composer trong thread | `form[data-chatgpt-composer][data-composer-placement="thread"]` |

Composer là ProseMirror, không phải textarea. `#prompt-textarea` cũ **không còn tồn tại**
trong DOM hiện tại (Observed: `web login` timeout với selector cũ trước khi cập nhật).

### 3.3 Landmark trạng thái

| Landmark | Selector | Khi nào |
|---|---|---|
| Đã đăng nhập | `button[aria-label="Open profile menu"]` | Có mặt trong phiên hợp lệ |
| Gửi | `form[data-chatgpt-composer] button[aria-label="Send"]` | Khi composer có nội dung |
| Đang stream | `button[aria-label="Stop"]` | Trong lúc phản hồi đang chạy |
| Chat mới | `button[aria-label="New chat"]` | Sidebar/header |
| Tin nhắn assistant | `h4[data-conversation-role="assistant"]` | Mỗi phản hồi đã render |

### 3.4 Sẵn sàng

`document.readyState === "complete"` **không đủ**. Trong một lần mở nguội sau khi dừng
Chrome, trang kẹt ở `readyState = "interactive"` và chưa có composer; `web state` timeout
ở `ready_expression`. Reload một lần thì pass, không cần đăng nhập lại.

Điều kiện sẵn sàng đã dùng:

```js
Array.from(document.querySelectorAll('form[data-chatgpt-composer] div.ProseMirror[contenteditable="true"]'))
  .some(function (element) {
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  })
```

## 4. Bản đồ DOM

| Landmark | Selector | Raw | Rendered | Ghi chú |
|---|---|---|---|---|
| Composer (toàn trang) | `form[data-chatgpt-composer] div.ProseMirror[contenteditable="true"]` | 2 | 1 | Home + thread cùng mount |
| Composer home | `form[data-chatgpt-composer][data-composer-placement="home"] div.ProseMirror` | 1 | 1 khi ở home | Ẩn khi ở thread |
| Send | `form[data-chatgpt-composer] button[aria-label="Send"]` | 2 | 1 | Nằm trong form |
| Stop | `button[aria-label="Stop"]` | 0–1 | 0–1 | Chỉ khi stream |
| New chat | `button[aria-label="New chat"]` | 1 | 1 | Luôn có trong phiên |
| Assistant | `h4[data-conversation-role="assistant"]` | N | M | N có thể > M do route cache |
| Profile | `button[aria-label="Open profile menu"]` | 1 | 1 | Dấu hiệu đăng nhập |

State matrix:

| Landmark | Home idle | Thread idle | Streaming | Signed out |
|---|---|---|---|---|
| Composer home | Render | Ẩn | Ẩn/Render tùy route | Không có |
| Composer thread | Ẩn | Render | Render | Không có |
| Send | Render (disabled nếu rỗng) | Render | Ẩn/đổi | Không có |
| Stop | Không có | Không có | Render | Không có |
| Assistant | 0 render | N render | N hoặc N+1 | Không có |
| Profile menu | Render | Render | Render | Không có |

`Send` disabled hay không chưa được đo riêng; script hiện tại gõ text trước rồi click nên
không phụ thuộc trạng thái disabled ban đầu.

## 5. Mô hình tương tác

1. **Focus**: click trusted vào composer (mouse event tại tâm match render đầu tiên).
2. **Nhập**: `Input.insertText` chèn toàn bộ text; ProseMirror nhận và cập nhật state.
3. **Gửi**: click trusted vào `button[aria-label="Send"]` trong form.
4. **Stream**: nút `Stop` xuất hiện; assistant heading có thể xuất hiện trước khi stream
   kết thúc.
5. **Kết thúc**: `Stop` biến mất; network quiet sau 2 s.
6. **Chat mới**: click `New chat`; route đổi về home; DOM cũ vẫn ẩn.

Quan sát thời lượng run cuối:

| Bước | Thời lượng |
|---|---|
| `count` | ~0.002 s |
| `type` (click focus + insertText) | ~5.04 s |
| `click` Send | ~1.20 s |
| `wait_count` | ~38.15 s |
| `wait_hidden` Stop | ~2.77 s |
| `wait_network_quiet` | ~2.00 s |
| Toàn turn | ~49.23 s |

`type` mất ~5 s dù `Input.insertText` là một lệnh; đây là chi phí click/focus và phản ứng
của SPA, không phải thời gian gõ từng ký tự. Đừng đặt timeout 5 s cho bước này.

## 6. Vòng đời phiên

```text
cold_boot
  └─ hydrating ──(composer render)──> ready_home
       └─(không có profile menu)──> auth_required ──(login tay)──> ready_home
ready_home
  └─ click New chat ──> resetting ──(assistant render = 0, home composer)──> ready_home
ready_home
  └─ type + Send ──> submitting ──(Stop render)──> streaming
streaming
  └─ Stop hidden + network quiet ──> settled_thread ──> ready_thread
any
  └─ mất profile menu / redirect login ──> auth_lost
```

| State | Tín hiệu Observed | Ghi chú |
|---|---|---|
| `hydrating` | `readyState` chưa complete, chưa có composer render | Có thể cần reload một lần |
| `ready_home` | Home composer render, assistant render = 0 | Trạng thái setup |
| `submitting` | Send click đã gửi, Stop chưa chắc đã render | Cửa sổ ngắn |
| `streaming` | `button[aria-label="Stop"]` render | Không dùng sleep |
| `settled_thread` | Stop hidden, network quiet | Điều kiện chấp nhận |
| `auth_lost` | Profile menu biến mất / redirect | Dừng, login tay |

## 7. Bản đồ network

Run cuối: **26 request**, **17 khớp** `network_patterns`. Bảng dưới chỉ ghi path, không
query string, không ID, không body.

| Path | Method | Pha | Vai trò (Inferred) |
|---|---|---|---|
| `/backend-api/settings/user` | GET | boot/send | Cấu hình người dùng |
| `/backend-api/settings/is_adult` | GET* | boot | Cờ cài đặt |
| `/backend-api/conversation/init` | GET* | boot | Khởi tạo conversation client |
| `/backend-api/me` | GET* | boot/send | Danh tính phiên |
| `/backend-api/accounts/check/v4-2023-04-27` | GET* | boot/send | Kiểm tra tài khoản/gói |
| `/backend-api/system_hints` | GET* | boot | Gợi ý UI |
| `/backend-api/prompt_library/` | GET | boot | Thư viện gợi ý prompt |
| `/backend-api/amphora/clear_settings_cache` | POST | boot | Xóa cache cài đặt |
| `/backend-api/amphora/notifications` | GET | boot | Thông báo |
| `/backend-api/user_segments` | GET | sau gửi | Phân khúc người dùng |
| `/backend-api/f/conversation/prepare` | POST | trước gửi | Chuẩn bị lượt |
| `/backend-api/sentinel/chat-requirements/prepare` | POST | trước gửi | Chuẩn bị integrity challenge |
| `/backend-api/sentinel/chat-requirements/finalize` | POST | trước gửi | Hoàn tất integrity challenge |
| `/backend-api/f/conversation` | POST | hành động | Gửi lượt; phản hồi stream |
| `/backend-api/conversations/{id}` | GET | sau gửi | Hydrate hội thoại |
| `/ces/v1/rgstr` | POST | nền | Telemetry (lặp nhiều lần, có 202) |
| `/ces/statsc/flush` | POST | nền | Telemetry flush |
| `wss://ws.chatgpt.com/...` | WebSocket | realtime | Kênh realtime (mục đích: Unknown) |

`*` = method `null` trong artifact do record `orphan: true`: response đến mà request bắt
đầu trước `begin_turn`. Không suy ra method từ `null`.

### 7.1 Diễn giải thứ tự

**Observed:** trong cửa sổ turn có một cụm bootstrap (settings, me, accounts), rồi
`prepare`, `sentinel prepare/finalize`, POST `f/conversation`, rồi
`conversations/{id}`. Telemetry `ces` xen giữa nhiều lần.

**Inferred:** `prepare` và `sentinel` là bước chuẩn bị/kiểm tra trước khi gửi; POST
`f/conversation` là hành động chính; GET `conversations/{id}` hydrate lại state sau khi
stream cập nhật. `f/conversation/prepare` xuất hiện hai lần; lần thứ hai có thể là chuẩn
bị cho lượt kế tiếp hoặc sau khi route đổi — chưa đủ bằng chứng để kết luận.

### 7.2 Telemetry và nhiễu

`/ces/v1/rgstr` lặp lại nhiều lần, có status 200/202 và có record `orphan`. Đây là
telemetry nền, không phải hành động người dùng. Vì `network_patterns` không chứa `/ces/`,
17 request khớp pattern đã loại phần lớn nhiễu; nhưng `wait_network_quiet` vẫn nhìn thấy
mọi event `Network.*`, nên telemetry dày có thể làm quiet khó đạt.

### 7.3 Dữ liệu nhạy cảm trong artifact

**Observed (run 2026-10-25 trước Phase 10):** `network.json` chứa `request_headers`,
`response_headers`, `request_body`; response `body` được lấy cho URL khớp
`network_patterns` (tối đa 4 MB/response). `sse.json` chứa `data`; `websocket.json` chứa
`payload`.

**Cập nhật Phase 10:** `network_patterns` chỉ còn lọc summary; body chỉ lấy theo
`body_capture_patterns`. Header nhạy cảm thành `[redacted]`; request body chỉ còn
metadata; SSE/WS mặc định chỉ metadata; probe body sample bị redact. Run mới
`20261025T133736Z-chatgpt` không còn raw body/stream. Chi tiết:
[`../../../report_chatgpt_chat_flow_20261025.md`](../../../report_chatgpt_chat_flow_20261025.md).

Do đó: không dán artifact vào báo cáo; chỉ trích path/method/status/body_bytes. Đây là lý
do `network_patterns` phải hẹp.

## 8. Truyền phát và realtime

| Kênh | Bằng chứng | Kết luận |
|---|---|---|
| EventSource | `probe.sse = 0`, `sse.json = []` | Không dùng EventSource trong run này |
| Fetch stream | `probe.network` có POST `f/conversation` via `fetch`; status 200 | Phản hồi chính stream qua fetch/ReadableStream |
| WebSocket | `probe.websocket = 1`; `wss://ws.chatgpt.com/...`; frames in/out; CDP 7 frame | Có kênh realtime song song |

`probe.websocket` metadata:

```text
state=1 (open), framesIn=2, framesOut=1, errors=0
```

**Unknown:** WebSocket dùng cho loại event nào (presence, cập nhật hội thoại, telemetry
hay tín hiệu khác). Không có payload trong báo cáo.

Kết luận quan trọng: **`sse=0` không phải lỗi**. Nếu chỉ nhìn con số này sẽ kết luận sai
là trang không stream. Phải đối chiếu `probe.network`, POST stream, `body_bytes`, và
WebSocket.

## 9. Tín hiệu integrity, fingerprint, anti-automation

**Observed:**

- Chuỗi `sentinel/chat-requirements/prepare` → `finalize` trong pha gửi.
- Telemetry `ces` lặp lại.
- Probe đọc fingerprint: `navigator.userAgent`, `language(s)`, `platform`,
  `hardwareConcurrency`, `deviceMemory`, `doNotTrack`, `devicePixelRatio`, `innerWidth`,
  `innerHeight`, `screen.*`.
- Probe gọi `WebGLRenderingContext.getParameter/getExtension`,
  `HTMLCanvasElement.getContext`, `matchMedia`, `localStorage.getItem`.
- `probe.calls` có `Performance.prototype.now` 17.699 lần,
  `getBoundingClientRect` 1.339 lần, `getComputedStyle` 1.227 lần.

**Inferred:** một phần là code UI/telemetry bình thường, một phần là tín hiệu integrity.
Không đủ bằng chứng để gọi tất cả là anti-bot.

**Quy tắc:** chỉ ghi nhận và tránh làm chain phụ thuộc vào chúng. Không vô hiệu hóa,
không replay token, không giả lập fingerprint, không vượt challenge.

## 10. Chuỗi hành động đã kiểm chứng

### 10.1 Setup — `new_chat`

| # | Action | Tiền điều kiện | Bất biến | Timeout |
|---|---|---|---|---|
| 0 | `click` `button[aria-label="New chat"]` | Đã đăng nhập, trang đã hydrate | Route chuyển về home | 30 s |
| 1 | `wait_hidden` `h4[data-conversation-role="assistant"]` | Sau click | Không còn assistant **render** | 30 s |
| 2 | `wait_visible` home composer | Sau reset | Composer home render | 30 s |

Vì sao chờ cả hai phía: chỉ chờ composer mới có thể thấy composer cũ; chỉ chờ assistant
biến mất có thể thấy home trước khi sẵn sàng.

### 10.2 Turn — `send_prompt`

| # | Action | Tiền điều kiện | Bất biến | Timeout |
|---|---|---|---|---|
| 0 | `count` assistant → `replies_before` | Home idle | Lưu số phản hồi render | 30 s |
| 1 | `type` composer với `{{prompt}}` | Home composer render | Text vào ProseMirror | 30 s |
| 2 | `click` Send trong form | Composer có text | Request gửi bắt đầu | 30 s |
| 3 | `wait_count` assistant > `replies_before` | Đã gửi | Có phản hồi mới render | 240 s |
| 4 | `wait_hidden` `button[aria-label="Stop"]` | Đang stream | UI báo stream xong | 240 s |
| 5 | `wait_network_quiet` 2000 ms | UI xong | Không còn network 2 s | 30 s |

Vì sao count delta: hội thoại có thể đã có phản hồi cũ; count tuyệt đối sai ngay từ lượt
hai.

Vì sao chờ Stop hidden: đây là tín hiệu UI trực tiếp của stream. Chờ Send biến mất không
đáng tin vì Send có thể vẫn hiện.

Vì sao thêm network quiet: Stop hidden có thể xảy ra trước chunk cuối; quiet 2 s chốt
trạng thái ổn định.

### 10.3 Kết quả

```text
run status: completed
steps:      6/6
page:       /c/{id}, readyState=complete
requests:   26 (17 khớp pattern)
exceptions: 0
console:    0
```

## 11. Sự cố đã gặp và bài học

| Sự cố | Nguyên nhân | Sửa |
|---|---|---|
| `web login` timeout | `#prompt-textarea` không còn tồn tại | Cập nhật selector ProseMirror/aria-label |
| Count/click nhầm | Route cũ còn trong DOM với `display:none` | Render-aware expressions + click match render đầu tiên |
| 13 exception `ReadableStreamDefaultReader.closed` | Env capture gọi getter trả promise, không gắn rejection handler | Gắn handler cho thenable trước khi encode |
| Cold start timeout | SPA chưa hydrate sau restart | Chờ/reload có kiểm soát; không auto-reload để tránh che lỗi auth |

## 12. Rủi ro

| Rủi ro | Mức | Phát hiện | Giảm thiểu |
|---|---|---|---|
| ChatGPT đổi DOM/aria-label | Cao | Login/ready timeout, count sai | Kiểm tra lại selector; ưu tiên `data-*` |
| A/B variant composer | Trung bình | Nhiều placement/route hơn | State matrix + selector container |
| Phiên hết hạn | Trung bình | Profile menu mất | `web login` tay; không tự động credential |
| Rate limit / giới hạn tài khoản | Trung bình | Lỗi 4xx/5xx, UI cảnh báo | Giảm số lượt; dừng khi có cảnh báo |
| Telemetry làm quiet timeout | Trung bình | `ces` lặp lại | Dùng tín hiệu UI hoặc tăng `ms` có kiểm soát |
| `network_patterns` quá rộng | Cao (dữ liệu) | Body bị lưu | Pattern hẹp; xóa artifact sau khi trích metadata |
| Cold start hydration | Trung bình | `state` timeout | Chờ/reload một lần; ghi caveat |
| Script-level timeout không enforce | Đã xử lý Phase 10 | Script chạy lâu hơn dự kiến | `ActionEngine` enforce deadline tổng + cap từng action |

## 13. Điều chưa biết

- WebSocket `ws.chatgpt.com` dùng cho event gì.
- Hành vi khi stream lỗi giữa chừng (retry UI, nút Regenerate, lỗi mạng).
- Hành vi với file đính kèm, voice, model picker, sharing.
- Giới hạn rate limit thực tế của tài khoản.
- A/B variant khác có cùng selector hay không.
- Vì sao `prepare` xuất hiện hai lần trong cùng turn.

Các mục này cần run riêng, có mission riêng, không suy đoán.

## 14. Code gate

- [x] State machine và tín hiệu từng state đã mô tả.
- [x] Selector đã kiểm tra raw/rendered ở home/thread.
- [x] Request ↔ hành động đã phân loại (Observed/Inferred).
- [x] Transport stream đã xác định: fetch-stream + WebSocket; không EventSource.
- [x] Tín hiệu hoàn tất UI + network đã rõ.
- [x] Chain không dùng sleep làm chờ chính.
- [x] Artifact chứng minh: 6/6 step, 0 exception, 0 console error.
- [x] Rủi ro và Unknown đã liệt kê.
- [x] Không có dữ liệu nhạy cảm trong báo cáo.
- [x] Người dùng đã đăng nhập và chấp nhận phạm vi thực nghiệm.

Kết luận: đủ điều kiện để duy trì `targets/chatgpt/` và action chain hiện tại. Mọi thay
đổi selector/chain sau này phải cập nhật lại báo cáo này hoặc tạo báo cáo thay thế.
