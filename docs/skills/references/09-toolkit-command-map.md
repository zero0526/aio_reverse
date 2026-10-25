# 09 — Bản đồ lệnh: aio-reverse, wre, MCP

Mục đích: một nơi tra cứu lệnh chính xác, tránh dùng sai primitive hoặc tạo thêm code
trùng chức năng.

## 1. Build và môi trường

```bash
# Sidecar Rust
cd libs/web-re-toolkit
cargo build --release -p wre-cli
./target/release/wre --version
cd ../..

# Python
uv sync

# Tùy chọn
export WRE_BIN=/absolute/path/to/wre
export AIO_DATA_DIR=/absolute/path/to/data
```

`WreToolkit` tìm binary theo thứ tự: đường dẫn truyền tay → `WRE_BIN` → build local →
`PATH`. Thiếu binary là lỗi, không fallback.

`AIO_DATA_DIR` đổi gốc `data/` (profiles, output, cache, db). Mặc định là
`<repo>/data`.

## 2. CLI `aio-reverse`

```bash
uv run aio-reverse web targets
uv run aio-reverse web scripts <target>
uv run aio-reverse web probe <target>
uv run aio-reverse web login <target> [--timeout 300]
uv run aio-reverse web run <target> [--setup-script NAME] [--script NAME] [--var NAME=VALUE] [--json]
uv run aio-reverse web session <target>
uv run aio-reverse web state <target>
uv run aio-reverse web click <target> <selector>
uv run aio-reverse web type <target> <text>
uv run aio-reverse web press <target> Enter|Escape|Tab|Backspace
uv run aio-reverse web evaluate <target> <expression>
uv run aio-reverse web navigate <target> <http(s)-url>
uv run aio-reverse web snapshot <target> --label <name> [--json]
uv run aio-reverse web skeleton --page A.html --page B.html [--xpath] [--json]
uv run aio-reverse mcp
uv run aio-reverse            # không tham số = MCP stdio
```

### 2.1 Ngữ nghĩa phiên

| Lệnh | Mở session | Ghi artifact | Giữ Chrome |
|---|---|---|---|
| `targets`, `scripts`, `probe` | Không | Không | Không |
| `login` | Có | Không | Có |
| `run` | Có | Có (`turn-NN/`) | Có |
| `session` | Không (chỉ status) | Không | Không |
| `state` | Có | Không | Có |
| `click`/`type`/`press`/`evaluate`/`navigate` | Có | Không | Có |
| `snapshot` | Có | Có (`snapshots/<utc>-<label>.html`) | Có |
| `skeleton` | Không (chỉ đọc file + gọi `wre`) | Không | Không |

Mỗi lệnh handover là one-shot: network/stream không được ghi giữa hai lệnh. Muốn đo
network, dùng `run` hoặc MCP session.

`web type` gõ vào element đang focus. `web click` trước nếu focus chưa đúng.

`web navigate` chỉ nhận URL http(s); sau navigate, probe được cài lại.

`web run` chạy setup scripts (không ghi artifact) rồi turn scripts (ghi artifact), cùng
một session. `--script` lặp lại được; mỗi script là một turn đo.

`web snapshot` ghi HTML vào `data/output/web/<target>/snapshots/` (gitignored), chặn
8 MiB fail loud, không ghi đè file cùng giây; CLI/MCP chỉ trả path + bytes + sha256,
không trả nội dung HTML. `web skeleton` cần ≥ 2 file `.html` ở **hai trạng thái khác
nhau** (home vs thread) — hai trang giống nhau cho skeleton vô dụng.

## 3. MCP tool

| Tool | Tham số | Việc |
|---|---|---|
| `web_targets` | — | Liệt kê target |
| `web_open` | `target` | Mở session, trả page + env |
| `web_run_script` | `target`, `script`, `variables?` | Chạy một turn đo, ghi artifact |
| `web_state` | `target` | Page + env |
| `web_inject_probe` | `target` | Cài lại `window.__WRE` nếu thiếu |
| `web_click` | `target`, `selector` | Click trusted |
| `web_type` | `target`, `text` | Gõ vào element đang focus |
| `web_press` | `target`, `key` | Enter/Escape/Tab/Backspace |
| `web_evaluate` | `target`, `expression` | Chạy JS |
| `web_navigate` | `target`, `url` | Điều hướng http(s) |
| `web_snapshot` | `target`, `label` | Chụp outerHTML, trả path/bytes/sha256 (không trả HTML) |
| `web_skeleton` | `pages` (≥ 2 `.html`), `xpath=false` | `wre template diff` → skeleton + slots |
| `web_close` | `target`, `keep_browser=true` | Đóng CDP; mặc định giữ Chrome |

`SessionRegistry` giữ một session/target, khóa mở trùng. Dùng MCP khi cần nhiều bước
handover giữ capture, hoặc khi agent cần điều khiển phiên sống. Tổng cộng **13 tool**.

## 4. `wre` — nhóm dùng trên đường recon

### 4.1 Browser

```bash
wre browser --port 9445 --start --status --profile data/profiles/<target>
wre browser --port 9445 --status
wre browser --port 9445 --stop
wre browser --port 9445 --start --headless --status
```

Luôn thêm `--status`: khi Chrome đã chạy, `--start` một mình có thể không in gì.

### 4.2 Probe

```bash
wre --json probe emit \
  --name __WRE \
  --preset fingerprint \
  --property Navigator.prototype.userAgent \
  --method Storage.prototype.getItem \
  --event click \
  --workers
```

Flags:

| Flag | Ý nghĩa |
|---|---|
| `--target <name>` | Đọc rules từ `targets/<name>.toml` (manifest Rust) |
| `--name <name>` | Tên object toàn cục, mặc định `__WRE` |
| `--preset fingerprint\|minimal\|none` | Mức trap |
| `--property holder.prop` | Trap thuộc tính, lặp lại |
| `--method holder.method` | Trap method, lặp lại |
| `--event <type>` | Đếm event, lặp lại |
| `--no-network` | Bỏ fetch/XHR/beacon |
| `--workers` | Trap Blob/Worker |
| `--no-stealth` | Không bảo vệ `Function.prototype.toString` |
| `--no-call-sites` | Không ghi stack site |
| `--no-sse` | Bỏ EventSource |
| `--no-websocket` | Bỏ WebSocket |
| `--json` | In `{name, source, bytes}` thay vì JS thô |

`--target` xung đột với `--preset`/các trap flag. Trap phải có dạng `holder.name`.

### 4.3 Env

```bash
wre env script --depth 4          # in JS, dùng để evaluate trong phiên sống
wre env snapshot <URL>            # CẢNH BÁO: navigate trang
wre env run <SCRIPT>              # chạy script trong realm từ snapshot
```

Trong phiên đang sống, chỉ dùng `env script` + `web evaluate`/`snapshot_env`. Không dùng
`env snapshot` giữa chain vì nó navigate và làm mất state.

### 4.4 Capture tĩnh

```bash
wre capture \
  --url https://example.test/ \
  --port 9333 \
  --wait 20 \
  --out data/captures/<name> \
  --keep-storage \
  --scripts \
  --profile data/profiles/capture-<name>
```

`capture` là static capture, **không** nằm trên đường `web run`. Dùng profile/port riêng
để tránh xung đột Chrome đang mở. `--no-probe` bỏ probe; `--proxy` cấu hình proxy;
`--headless` chạy ẩn.

### 4.5 Marker / pool / sweep (Phase B)

```bash
wre markers --kind <kind> --group <group> --json
wre pools --group <group> --one-at-a-time --json
wre sweep --baseline <path> --baseline <path> --arm <name>:<path> --json
```

Đây là công cụ attribution marker, ngoài đường recon chính. Không dùng thay cho
`web run` khi mục tiêu là mô tả hành vi trang.

## 5. `wre` — nhóm phân tích tĩnh (tùy chọn)

Các lệnh này phân tích script/bundle, không điều khiển trang:

| Lệnh | Mục đích |
|---|---|
| `init` | Ghi target manifest |
| `targets` | Liệt kê manifest |
| `check` | Kiểm tra manifest |
| `discover` | Tìm surface trong tài liệu, không cần browser |
| `pin` | Giữ capture qua lần xóa artifact |
| `show` | Tóm tắt capture |
| `deobf`, `beautify`, `passes` | Pipeline deobfuscation |
| `surface` | Báo surface mà mỗi function chạm tới |
| `mount` | Tìm primitive của target và gọi |
| `client` | Bundle/binary/language package |
| `vm`, `wire` | Workbench VM/payload |
| `sandbox` | Surface realm trình bày |
| `tls` | Transport fingerprint |
| `diff`, `baseline` | So sánh map |
| `locate`, `drift`, `builds`, `align` | Định vị/theo dõi thay đổi giữa build |
| `integrity`, `equivalent`, `grade` | Kiểm tra hash/rewrite/chấm payload |
| `template` | Induct template HTML |
| `verify` | Chạy check không cần browser |

Chỉ dùng khi mục tiêu là phân tích bundle/script. Không trộn với recon DOM/network trừ
khi báo cáo nêu rõ.

## 6. Đường dẫn dữ liệu

```text
data/profiles/<target>/                       Chrome profile bền
data/output/web/<target>/<run_id>/            artifact
data/captures/<name>/                         capture tĩnh
data/workspace/                               workspace toolkit
data/cache/                                   cache
data/db/                                      SQLite (nếu dùng)
```

`data/profiles/` và `data/output/` phải gitignored. Không commit artifact.

## 7. Exit code và lỗi

- `aio-reverse` trả `1` khi gặp `AioReverseError`, `ValueError`, `FileNotFoundError`,
  in `error: ...` ra stderr.
- `wre` trả mã lỗi khác 0 khi command fail; `WreToolkit` raise `ToolkitError` kèm
  command/returncode/stderr.
- Không bắt rồi trả default. Sửa nguyên nhân hoặc báo lỗi.

## 8. Luồng mẫu

### Recon DOM

```bash
uv run aio-reverse web targets
uv run aio-reverse web state <target>
uv run aio-reverse web evaluate <target> "document.title"
# inventory selector, state matrix...
```

### Một lượt đo

```bash
uv run aio-reverse web login <target>
uv run aio-reverse web run <target> --script <turn> --var prompt="ping"
# đọc data/output/web/<target>/<run_id>/
```

### Handover nhiều bước (MCP)

```text
web_targets
web_open(target)
web_evaluate(target, expression)
web_click(target, selector)
web_type(target, text)
web_press(target, "Enter")
web_state(target)
web_close(target, keep_browser=true)
```

## 9. An toàn khi dùng lệnh

- `web evaluate` có quyền chạy JS trong trang; chỉ dùng biểu thức read-only trong recon.
- `web navigate` chỉ http(s), nhưng vẫn có thể rời phạm vi mission; kiểm tra URL.
- `web click` có thể kích hoạt hành động thật; xác nhận mission trước.
- `wre capture` mở trang thật; dùng profile riêng và thời gian chờ hợp lý.
- Không chạy `wre env snapshot` giữa chain đang giữ state.
