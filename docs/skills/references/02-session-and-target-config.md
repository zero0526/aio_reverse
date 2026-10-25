# 02 — Phiên, profile và cấu hình target

Mục đích: dựng một phiên Chrome bền, đăng nhập bằng tay, và khai báo target đủ để
`web run` mở đúng trang, chờ đúng trạng thái, và cài đúng probe.

## 1. Chuẩn bị một lần

```bash
# Build sidecar Rust (chỉ cần khi chưa có binary)
cd libs/web-re-toolkit
cargo build --release -p wre-cli
./target/release/wre --version
cd ../..

# Cài dependency Python
uv sync
```

Thứ tự tìm binary của `WreToolkit`:

1. Đường dẫn truyền tay.
2. Biến môi trường `WRE_BIN`.
3. `libs/web-re-toolkit/target/{release,debug}/wre`.
4. `wre` trên `PATH`.

## 2. Mô hình phiên

```text
data/profiles/<target>/     Chrome user-data-dir bền (cookie, localStorage)
data/output/web/<target>/   Artifact từng run (gitignored)
```

- Profile bền nghĩa là đăng nhập một lần, các lần sau không cần login lại.
- `web login` mở Chrome, chờ `login_expression`, rồi đóng CDP nhưng **giữ Chrome**.
- `web run` mở lại session, kiểm tra `ready_expression`, kiểm tra `login_expression`,
  cài probe, chạy script.
- `web state`, `web click`, `web evaluate`… là one-shot: mở session, làm một việc, đóng
  CDP, giữ Chrome.
- MCP giữ session sống theo target, phù hợp handover nhiều bước.

Port mặc định của target là `chrome_port` (ví dụ ChatGPT dùng `9445`). Hai target không
được dùng cùng port nếu chạy đồng thời.

## 3. Cấu trúc target

```text
targets/<name>/
├── target.json
├── README.md            # tùy chọn: selector đã xác nhận, cảnh báo
└── scripts/
    ├── <setup>.json
    └── <turn>.json
```

`TargetRegistry` quét cố định `PROJECT_ROOT/targets/*/target.json`. Tên trong JSON phải
khớp tên thư mục. Mọi script được liệt kê phải tồn tại; thiếu file là lỗi load target.

## 4. Trường `target.json`

| Trường | Bắt buộc | Ý nghĩa |
|---|---|---|
| `name` | có | Phải khớp tên thư mục |
| `entry_url` | có | URL mở khi bắt đầu run; phải là http(s) |
| `login_url` | có | URL mở khi `web login` |
| `login_expression` | có | Biểu thức JS trả `true` khi đã đăng nhập |
| `ready_expression` | có | Biểu thức JS trả `true` khi UI sẵn sàng |
| `network_patterns` | không | Chuỗi con để lọc request trong summary |
| `env_depth` | không | Độ sâu snapshot môi trường, mặc định 4 |
| `chrome_port` | không | Cổng CDP, mặc định 9333 |
| `setup_scripts` | không | Chạy trước các lượt đo, không ghi artifact |
| `turn_scripts` | không | Script đo mặc định |
| `probe` | không | Cấu hình Rust probe |

### 4.1 `login_expression`

- Chỉ đọc, không tạo side effect, không gửi request.
- Nên kiểm tra một landmark chỉ xuất hiện khi đã đăng nhập (menu tài khoản, avatar).
- Có thể chỉ cần presence; không nhất thiết render, vì mục tiêu là phân biệt phiên.

Ví dụ:

```js
document.querySelector('button[aria-label="Open profile menu"]') !== null
```

### 4.2 `ready_expression`

- Phải kiểm tra **phần tử đã render**, không chỉ tồn tại trong DOM.
- Phải là ứng dụng đã hydrate, không chỉ `document.readyState === "complete"`.
- Tránh biểu thức quá chặt khiến A/B variant làm gãy; nhưng không nới đến mức chấp
  nhận skeleton.

Ví dụ render-aware:

```js
Array.from(document.querySelectorAll('form[data-chatgpt-composer] div.ProseMirror[contenteditable="true"]'))
  .some(function (element) {
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  })
```

### 4.3 `network_patterns`

Dùng để giảm nhiễu trong `summary.json` và `matched_requests`. Chọn path đặc trưng của
nghiệp vụ, bỏ telemetry:

```json
["/backend-api/", "/conversation", "/sentinel/"]
```

Đây chỉ là bộ lọc báo cáo. `network.json` vẫn ghi mọi request CDP thấy.

### 4.4 `probe`

| Khóa | Mặc định | Ý nghĩa |
|---|---|---|
| `preset` | `fingerprint` | `fingerprint`, `minimal`, `none` |
| `properties` | `[]` | `holder.property`, ví dụ `Navigator.prototype.userAgent` |
| `methods` | `[]` | `holder.method`, ví dụ `Storage.prototype.getItem` |
| `events` | `[]` | Loại event cần đếm |
| `network` | `true` | Ghi `fetch`/XHR/beacon |
| `workers` | `true` | Trap Blob/Worker |
| `stealth` | `true` | Giữ `Function.prototype.toString` tự nhiên |
| `call_sites` | `true` | Ghi stack site cho reads/calls/events |
| `sse` | `true` | Ghi `EventSource` |
| `websocket` | `true` | Ghi WebSocket metadata |

Preset gợi ý:

- `fingerprint`: đủ để thấy trang đọc gì, gọi gì, network, SSE/WS.
- `minimal`: ít nhiễu, chỉ network + stream.
- `none`: tắt trap; chỉ dùng CDP.

Probe được cài bằng `Page.addScriptToEvaluateOnNewDocument` + evaluate ngay. Sau mỗi
navigation phải cài lại; `InteractiveSession.navigate` làm việc này tự động.

## 5. Lệnh vận hành

```bash
uv run aio-reverse web targets
uv run aio-reverse web scripts <target>
uv run aio-reverse web probe <target> > /tmp/probe.js
node --check /tmp/probe.js

uv run aio-reverse web login <target>          # người thật đăng nhập
uv run aio-reverse web state <target>          # page + env
uv run aio-reverse web session <target>        # trạng thái Chrome/CDP

uv run aio-reverse web evaluate <target> "document.title"
uv run aio-reverse web click <target> "<selector>"
uv run aio-reverse web type <target> "<text>"  # gõ vào element đang focus
uv run aio-reverse web press <target> Enter    # Enter/Escape/Tab/Backspace
uv run aio-reverse web navigate <target> "https://example.test/path"
```

`web type` **không** tự chọn element. Trong action script, action `type` tự click vào
selector trước khi insert text; trong handover, phải `web click` trước.

## 6. MCP

```bash
uv run aio-reverse          # không tham số = MCP stdio
uv run aio-reverse mcp
```

11 tool:

`web_targets`, `web_open`, `web_run_script`, `web_state`, `web_inject_probe`,
`web_click`, `web_type`, `web_press`, `web_evaluate`, `web_navigate`, `web_close`.

`SessionRegistry` giữ một session sống mỗi target, khóa mở trùng, `close_all` khi server
dừng. Dùng MCP khi cần chuỗi handover giữ nguyên network/console capture giữa các bước.

## 7. Lỗi cấu hình thường gặp

| Lỗi | Nguyên nhân |
|---|---|
| `unknown key` | Sai tên trường trong `target.json`/`probe` |
| `name does not match directory` | `name` khác tên thư mục |
| `script ... does not exist` | Script được liệt kê nhưng thiếu file |
| `must be an http(s) URL` | URL sai scheme hoặc thiếu host |
| `probe.preset must be one of ...` | Preset ngoài `fingerprint|minimal|none` |
| `holder.name` | Trap thiếu dấu chấm phân tách |

Tất cả đều fail loud khi load. Không sửa bằng try/except trong code gọi.

## 8. Checklist cổng 1

- [ ] `web targets` thấy target.
- [ ] `web scripts` thấy setup/turn script.
- [ ] Probe sinh ra và qua `node --check`.
- [ ] `web login` pass bằng đăng nhập tay.
- [ ] `web state` trả page + env, không cần login lại.
- [ ] `login_expression`/`ready_expression` đã thử ở trạng thái home và thread.
- [ ] Không có credential trong repo.
