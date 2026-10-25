---
name: web-surface-recon
description: Authorized, evidence-first reconnaissance of a live web page and design of a JSON action chain to reach a goal with aio-reverse/wre. Use when asked to analyze how a web app behaves, map its DOM/network/streams, build or repair targets/<name> configuration and action scripts, or require a behavior report before writing integration code.
---

# Web Surface Recon

Skill này biến một trang web chưa biết thành hai thứ có thể kiểm chứng:

1. **Behavior report** — trang hoạt động thế nào, bằng chứng nào chứng minh.
2. **Action chain JSON** — chuỗi hành động tối thiểu để đạt một mục tiêu, chạy được
   bằng `aio-reverse web run`.

Đây là skill **tài liệu + quy trình**, không phải lệnh sửa engine. Mọi phân tích dùng
crate Rust qua sidecar `wre` và lớp wrapper Python hiện có. Không thêm primitive mới,
không viết lại probe, không vá trang bằng JavaScript tùy ý để che lỗi.

Ca thực nghiệm đầy đủ: [`examples/chatgpt/behavior-report.md`](examples/chatgpt/behavior-report.md).

## Danh mục module

| Tình huống | Đọc module |
|---|---|
| Mở target mới | `01` → `02` → `03` |
| DOM/selector gãy | `03` + `08` |
| Chain timeout hoặc đếm sai | `04` + `08` |
| Network/stream khó hiểu | `05` |
| Cần chứng minh bằng artifact | `06` |
| Viết báo cáo trước khi code | `07` + template |
| Tra lệnh CLI/MCP/`wre` | `09` |
| Phân tích HTML, bóc boilerplate & AutoCrawl | `10` |
| Học từ ca ChatGPT | `examples/chatgpt/*` |

## Non-negotiables

- Chỉ phân tích tài khoản bạn sở hữu hoặc được phép kiểm thử; tuân thủ ToS và rate limit.
- Đăng nhập do người thật thực hiện. Không lưu, không tự động hóa credential/cookie/token.
- Không ghi cookie, token, request/response body, prompt thật hay nội dung hội thoại vào
  tài liệu. Chỉ ghi **metadata, đường dẫn endpoint, schema quan sát được**.
- Không vượt CAPTCHA, anti-bot, paywall hay giới hạn quyền. Ghi nhận tín hiệu và dừng.
- Fail loud: thiếu selector, timeout, sai trạng thái thì báo đúng bước và selector; cấm
  fallback im lặng.
- Không sửa code engine trong lúc recon. Nếu thiếu primitive, ghi "gap" vào báo cáo và
  dừng; chỉ mở task code khi người dùng duyệt.
- `data/profiles/` và `data/output/` là dữ liệu cục bộ, đã gitignore. Không commit.

## Quy tắc vàng: report trước, code sau

Thứ tự bắt buộc:

```text
Mission → Session → Surface map → Behaviour map → Action chain design
        → Dry run → Measured run → Artifact forensics → Report → Code gate
```

Không được viết code tích hợp (target mới, script mới, sửa adapter) trước khi báo cáo
hành vi có đủ 11 mục ở [`references/07-behavior-report.md`](references/07-behavior-report.md)
và được người dùng chấp nhận.

## Bảy cổng thực thi

### Cổng 0 — Mission contract

Xác định rõ:

| Trường | Câu hỏi |
|---|---|
| Goal | Một câu: đạt được gì, quan sát được bằng gì? |
| Target | Origin, route, tài khoản nào, thuộc quyền ai? |
| Allowed | Hành động được phép: mở trang, gõ, gửi, đọc metadata? |
| Forbidden | Mua, xóa, gửi tiền, đổi quyền, spam, scrape hàng loạt? |
| Evidence | Artifact nào chứng minh thành công? |
| Stop | Điều kiện dừng: mất phiên, gặp CAPTCHA, thấy dữ liệu lạ? |

Xem [`references/01-authorization-and-scope.md`](references/01-authorization-and-scope.md).

### Cổng 1 — Session & target config

Một target được khai báo hoàn toàn bằng `targets/<name>/target.json` + `scripts/*.json`.
Chrome dùng profile bền `data/profiles/<name>/`; đăng nhập một lần bằng tay.

```bash
uv run aio-reverse web targets
uv run aio-reverse web scripts <target>
uv run aio-reverse web probe <target> > /tmp/probe.js && node --check /tmp/probe.js
uv run aio-reverse web login <target>
uv run aio-reverse web state <target>
```

Điều kiện vào cổng: `login_expression` và `ready_expression` đã kiểm chứng trên DOM
thật; `web state` trả page + env snapshot mà không cần đăng nhập lại.

Xem [`references/02-session-and-target-config.md`](references/02-session-and-target-config.md).

### Cổng 2 — Surface map (DOM)

Lập bản đồ **chỉ đọc** trước khi gửi bất cứ thứ gì:

1. Nhận diện trang: URL, title, `readyState`, có bao nhiêu workspace/route đang mount.
2. Liệt kê landmark: form, input, contenteditable, button, heading, menu.
3. Phân loại trạng thái: home, thread, streaming, lỗi, đăng xuất.
4. Tìm bản trùng bị ẩn: selector khớp nhiều node nhưng chỉ một node được render.
5. Xác định cơ chế nhập: textarea, contenteditable, ProseMirror, shadow DOM?
6. Chốt selector theo thứ tự ưu tiên: `data-*` → `aria-label`/`role` → text ổn định
   → cấu trúc CSS. Không dùng class hash/generated.

Điều kiện vào cổng: mỗi selector hành động có **số match thô** và **số match render**,
kèm trạng thái nào thì nó xuất hiện.

**Skeleton-first (khuyên dùng trước khi inventory thủ công):** chụp hai trạng thái
khác nhau bằng `web snapshot <target> --label home` / `--label thread`, rồi
`web skeleton --page A.html --page B.html --xpath`. Cấu trúc tĩnh bị prune, node
`← [dynamic]` và `slots` chỉ đúng vùng nội dung đổi theo dữ liệu — inventorY thủ công
chỉ cần làm trong các vùng đó. Hai snapshot **phải ở hai trạng thái khác nhau**,
nếu giống nhau mọi node sẽ "stable" và skeleton vô dụng.

Xem [`references/03-surface-mapping.md`](references/03-surface-mapping.md).

### Cổng 3 — Behaviour map (network + stream + state)

Phân biệt ba lớp bằng chứng:

| Lớp | Nguồn | Dùng để |
|---|---|---|
| CDP Network | `turn-NN/network.json` | Mọi request, thứ tự, status, body bytes |
| Rust probe | `turn-NN/probe.json` | Ai gọi `fetch`/XHR/beacon, đọc gì, gọi hàm gì |
| Stream | `probe.json` + `sse.json` + `websocket.json` | SSE thật, WebSocket, fetch-stream |

Phải trả lời được:

- Request nào là bootstrap, request nào là hành động, request nào là telemetry?
- Phản hồi stream bằng `EventSource`, WebSocket hay `fetch` + `ReadableStream`?
- Tín hiệu "xong" của UI là gì: nút Stop biến mất, count tăng, network quiet?
- Có tín hiệu anti-automation nào (sentinel/challenge/telemetry) cần ghi nhận?

`probe.sse == 0` **không** đồng nghĩa không có stream. Đó là lỗi suy luận phổ biến.

Xem [`references/05-network-and-stream-analysis.md`](references/05-network-and-stream-analysis.md).

### Cổng 4 — Action chain design

Thiết kế chuỗi theo mô hình:

```text
preconditions → setup → step 1..N → completion invariant → cleanup
```

Mỗi bước phải có:

- **Tiền điều kiện** (trang đang ở trạng thái nào).
- **Hành động** (một trong 11 action type).
- **Bất biến sau bước** (điều gì phải đúng).
- **Timeout** và **tín hiệu lỗi**.

Mẫu bắt buộc cho thao tác gửi:

1. `count` mốc trước khi gửi, lưu biến.
2. `type` (tự click focus rồi `Input.insertText`).
3. `click` submit.
4. `wait_count > mốc` (không dùng count tuyệt đối).
5. `wait_hidden` tín hiệu đang xử lý (nút Stop).
6. `wait_network_quiet` để chốt stream.

Không dùng `sleep` làm cơ chế chờ chính. Không reload để che lỗi auth/UI.

Xem [`references/04-action-chain-design.md`](references/04-action-chain-design.md).

### Cổng 5 — Dry run

Chạy từng bước bằng handover, không ghi artifact:

```bash
uv run aio-reverse web state <target>
uv run aio-reverse web evaluate <target> "<read-only expression>"
uv run aio-reverse web click <target> "<selector>"
uv run aio-reverse web type <target> "<text>"
uv run aio-reverse web press <target> Enter
```

Lưu ý: mỗi lệnh handover là một phiên one-shot. Network/stream không được ghi lại giữa
hai lệnh; muốn đo network phải dùng `web run` hoặc MCP session sống.

### Cổng 6 — Measured run

```bash
uv run aio-reverse web run <target> --script <name> --var name=value
```

Đọc ngay output tổng hợp:

```text
turns ... setup_steps ... steps ...
requests ... matched ... sse ... ws ... console_errors ... exceptions ...
probe reads ... calls ... events ... network ... sse ... websocket ...
```

Điều kiện vào cổng: `steps` đủ, `exceptions=0`, `console_errors=0`, artifact đầy đủ,
và mọi con số bất thường đã được giải thích bằng bằng chứng.

Xem [`references/06-artifact-forensics.md`](references/06-artifact-forensics.md).

### Cổng 7 — Behavior report & code gate

Báo cáo phải tách rõ **Observed / Inferred / Unknown**. Không biến suy luận thành sự thật.

Chỉ sau khi báo cáo trả lời được:

- Trang đang chạy theo state machine nào?
- Request nào tương ứng với hành động nào?
- Stream đi bằng transport nào?
- Chuỗi hành động dựa trên tín hiệu nào, không dựa vào sleep?
- Artifact nào chứng minh?
- Rủi ro nào sẽ làm chain gãy?

thì mới được viết code.

Xem [`references/07-behavior-report.md`](references/07-behavior-report.md).

## Bản đồ lệnh tối thiểu

| Việc | Lệnh |
|---|---|
| Liệt kê target | `uv run aio-reverse web targets` |
| Liệt kê script | `uv run aio-reverse web scripts <target>` |
| Sinh probe Rust | `uv run aio-reverse web probe <target>` |
| Đăng nhập tay | `uv run aio-reverse web login <target>` |
| Trạng thái + env | `uv run aio-reverse web state <target>` |
| Đọc DOM | `uv run aio-reverse web evaluate <target> "<expr>"` |
| Click / gõ / phím | `web click` / `web type` / `web press` |
| Điều hướng | `uv run aio-reverse web navigate <target> <http(s)-url>` |
| Chụp HTML snapshot của trạng thái | `uv run aio-reverse web snapshot <target> --label <name>` |
| Skeleton từ 2 snapshot | `uv run aio-reverse web skeleton --page A.html --page B.html --xpath` |
| Chạy đo | `uv run aio-reverse web run <target> --script <name>` |
| MCP stdio | `uv run aio-reverse` hoặc `uv run aio-reverse mcp` |

Bản đầy đủ, gồm cả `wre` CLI và MCP tool:
[`references/09-toolkit-command-map.md`](references/09-toolkit-command-map.md).

Phân tích HTML vi phân, bóc boilerplate và tự động sinh selectors cho AutoCrawl:
[`references/10-html-processing-and-autocrawl.md`](references/10-html-processing-and-autocrawl.md).

## Khung target tối thiểu

```json
{
  "name": "<target>",
  "entry_url": "https://example.test/",
  "login_url": "https://example.test/",
  "login_expression": "document.querySelector('<signed-in-marker>') !== null",
  "ready_expression": "document.querySelector('<visible-composer>') !== null",
  "network_patterns": ["/api/"],
  "env_depth": 4,
  "chrome_port": 9445,
  "setup_scripts": ["<setup>"],
  "turn_scripts": ["<turn>"],
  "probe": {
    "preset": "fingerprint",
    "properties": [],
    "methods": [],
    "events": [],
    "network": true,
    "workers": true,
    "stealth": true,
    "call_sites": true,
    "sse": true,
    "websocket": true
  }
}
```

Template đầy đủ: [`templates/target.json`](templates/target.json) và
[`templates/action-script.json`](templates/action-script.json).

## Bảng quyết định nhanh khi selector gãy

| Quan sát | Nghĩa | Bước tiếp theo |
|---|---|---|
| `querySelectorAll` khớp 0 | Selector sai hoặc DOM chưa render | Kiểm tra trạng thái, liệt kê lại landmark |
| Khớp > 0 nhưng `wait_visible` fail | Toàn bộ match bị ẩn | Tìm route cache / bản sao `display:none` |
| Click đúng node nhưng không có hiệu ứng | Node không nhận pointer hoặc bị phủ | Kiểm tra `getBoundingClientRect`, element tại tâm |
| Count tăng nhưng UI không đổi | Đếm bản ẩn hoặc sai landmark | Dùng count render-aware + state matrix |
| Login timeout | Hết phiên hoặc `login_expression` sai | `web login` lại bằng tay; không tự động credential |
| Ready timeout sau restart | SPA chưa hydrate | Chờ thêm, reload có kiểm soát, ghi nhận caveat |
| `probe.sse == 0` | Có thể stream bằng fetch | Kiểm tra POST stream + WebSocket + CDP |
| Network quiet timeout | Có polling/telemetry nền | Lọc pattern hoặc chờ tín hiệu UI thay thế |

Đầy đủ: [`references/08-failure-playbook.md`](references/08-failure-playbook.md).

## Cấu trúc gói

| Đường dẫn | Nội dung |
|---|---|
| `references/01-*` | Hợp đồng nhiệm vụ, quyền, dữ liệu, điều kiện dừng |
| `references/02-*` | Profile, target.json, probe config, CLI/MCP |
| `references/03-*` | Bản đồ DOM, visibility, selector ranking |
| `references/04-*` | Thiết kế action chain, template, save, timeout |
| `references/05-*` | Network, SSE/WS/fetch-stream, telemetry, anti-automation |
| `references/06-*` | Đọc artifact, kiểm tra drain, tiêu chí chấp nhận |
| `references/07-*` | Mẫu báo cáo hành vi + code gate |
| `references/08-*` | Playbook lỗi thường gặp |
| `references/09-*` | Bản đồ lệnh `aio-reverse`, `wre`, MCP |
| `templates/*` | Khung báo cáo, target, action script |
| `examples/chatgpt/*` | Ca thực nghiệm ChatGPT: DOM, network, chain, bài học |

## Cài như skill của Qoder (tùy chọn)

`docs/skills` là nguồn tài liệu trong repo. Nếu muốn Qoder tự nạp:

```bash
mkdir -p .qoder/skills
ln -s ../../docs/skills .qoder/skills/web-surface-recon
```

Tên symlink phải là `web-surface-recon` để khớp `name` trong frontmatter.
