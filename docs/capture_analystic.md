# Capture & phân tích luồng chat — kiến trúc hiện tại và trạng thái triển khai

> Mốc tham chiếu: working tree ngày **2026-10-25**, các thay đổi **chưa commit**.
> Tài liệu này thay thế bản mô tả kiến trúc `ProbeMode` / `TurnSpec` / `FlowRunner` cũ.
> Các symbol cũ đã bị xóa khỏi repo; xem mục 7 để biết chúng được thay bằng gì.

## 0. Tóm tắt trạng thái

| Hạng mục | Trạng thái | Ghi chú |
|---|---|---|
| Rust probe SSE/WebSocket + `drain()` | Xong | `cargo test -p wre-probe`: 15 test |
| `wre probe emit` + `--profile` | Xong | `cargo test -p wre-target -p wre-cli`: 9 test |
| Target JSON tại repo-root | Xong | `targets/<name>/target.json` + `scripts/*.json` |
| Action script JSON + template/save | Xong | 11 action type, fail loud khi thiếu biến |
| CDP adapter tách package + `drain_probe` | Xong | `adapters/web/cdp/` (7 module) |
| `ActionEngine` + `InteractiveSession` | Xong | Phiên Chrome sống lâu, probe inject một lần |
| Use case `RunWebScripts` + artifact JSON | Xong | `data/output/web/<target>/<run_id>/` |
| CLI `aio-reverse web ...` | Xong | 12 lệnh con + `mcp` |
| MCP server (stdio) | Xong | 11 tool web, session registry một phiên/target |
| Dọn kiến trúc cũ | Xong | `ProbeMode`, `TurnSpec`, `FlowRunner`, `CHAT_PROBE_JS` đã xóa |
| Unit tests Python | Xong | **116 test pass**, không cần Chrome/wre thật |
| E2E fakechat + MCP | Xong | 2 lượt, `drain()` đúng, 11 tool |
| Chạy `chatgpt.com` thật | Xong | Login tay 1 lần; run `20261025T115909Z-chatgpt`; restart Chrome vẫn giữ đăng nhập |
| Primitive chỉ xét phần tử render | Xong | `click`/`count`/`wait_*` lọc `display:none` + kích thước 0 |
| Env capture không tạo unhandled rejection | Xong | Getter trả promise được gắn rejection handler (`wre-env`) |
| Phase B: marker sweep | Chưa làm | Toolkit đã có `markers`/`pools`/`sweep` |
| Ghi DB | Không dùng | Artifact JSON là source of truth |

## 1. Mục tiêu & quyết định kiến trúc

Mục tiêu: **Rust sở hữu probe và browser primitive; Python là lớp wrapper mỏng** cho cấu hình
mục tiêu, action script, phiên Chrome bền, artifact và handover cho agent.

Quyết định đã chốt:

1. **`wre` CLI là sidecar process** tới các crate. Python không link Rust, không PyO3,
   không sửa crate.
2. **Một nguồn probe duy nhất là Rust.** Python gọi `wre probe emit` để lấy JS, inject bằng
   `Page.addScriptToEvaluateOnNewDocument` + evaluate ngay, rồi `drain()` mỗi lượt.
   Không còn probe JavaScript viết tay trong Python.
3. **Target là dữ liệu, không phải code.** Mỗi target là `targets/<name>/target.json` cộng
   các action script JSON; thêm target mới không cần sửa Python.
4. **Mỗi lượt là một action script JSON**, không hardcode selector/turn logic trong Python.
5. **Phiên Chrome sống lâu**, profile bền tại `data/profiles/<target>/`; đóng process không
   làm mất đăng nhập.
6. **Human-in-the-loop:** người dùng đăng nhập thủ công một lần; không tự động hóa credential.
7. Mọi lỗi CLI/JSON/probe/login/timeout đều raise có ngữ cảnh; không fallback âm thầm.

Phân chia trách nhiệm:

| Lớp | Sở hữu |
|---|---|
| `wre probe emit` | Sinh JS stealth probe (reads/calls/events/network/SSE/WebSocket) |
| `wre browser` | Launch/attach Chrome, profile bền theo `--profile` |
| `wre capture` | Static capture + bundle (tùy chọn, không nằm trên đường chạy chính) |
| `wre env script` | Sinh JS snapshot environment (Python chỉ eval) |
| `wre markers` / `pools` / `sweep` | Catalog marker, thiết kế pool, diff offline |
| Python CDP | Điều khiển phiên, input tin cậy, Network/SSE/WS, `drain_probe` |
| Python application | `ActionEngine`, `InteractiveSession`, use case, artifact |
| Python adapters | CLI, MCP server, session registry |

## 2. Kiến trúc đích

```text
Agent / người dùng
   │  (MCP stdio)                     (CLI)
   ▼                                    ▼
adapters/mcp/*                    cli/web_*.py
   └──────────┬──────────────────────────┘
              ▼
   composition.py (wiring dùng chung)
              │
              ▼
   application: InteractiveSession + ActionEngine
              │
      ┌───────┼───────────────────────┐
      ▼       ▼                       ▼
IToolkitPort  IBrowserSessionPort   IRunStore
(wre CLI)     (CDP adapter)          (artifact JSON)
      │             │
      ▼             ▼
wre probe emit   Chrome CDP (WebSocket)
wre browser --profile
```

Luồng dữ liệu probe:

```text
target.json.probe
   → WreToolkit.emit_probe()        # gọi `wre probe emit --json`
   → Page.addScriptToEvaluateOnNewDocument(source)
   → Runtime.evaluate(source)        # áp cho document hiện tại
   → kiểm tra window.__WRE.drain
   → mỗi lượt: window.__WRE.drain()  # trả snapshot rồi reset counter
```

## 3. Bản đồ code

### 3.1 Target configuration và action script

| Nội dung | Vị trí |
|---|---|
| Dữ liệu ChatGPT | `targets/chatgpt/target.json` |
| Script mặc định | `targets/chatgpt/scripts/{new_chat,send_prompt}.json` |
| Ghi chú selector | `targets/chatgpt/README.md` |
| Target E2E cục bộ | `targets/fakechat/target.json` + `tests/fixtures/fake_chat_server.py` |
| `TargetProbeConfig` (preset, trap list, cờ stream) | `src/aio_reverse/targets/web_target.py:29` |
| `WebTargetSpec` (URL, pattern, port, script group) | `src/aio_reverse/targets/web_target.py:58` |
| Validate bất biến | `src/aio_reverse/targets/web_target.py:74` |
| `origin`, `script_path` | `src/aio_reverse/targets/web_target.py:105,109` |
| Loader strict, unknown key → lỗi | `src/aio_reverse/targets/target_loader.py:51` |
| Registry quét `targets/*/target.json` | `src/aio_reverse/targets/target_registry.py:11` |
| 11 action type + whitelist phím | `src/aio_reverse/targets/action_script.py:23,18` |
| Template `{{var}}` và `required_variables()` | `src/aio_reverse/targets/action_script.py:88,192` |
| Render tại runtime `resolve_action()` | `src/aio_reverse/targets/action_script.py:217` |
| Loader + resolve path script | `src/aio_reverse/targets/action_script_loader.py:21` |
| Helper đọc JSON strict dùng chung | `src/aio_reverse/targets/json_document.py` |

Quy tắc validate đáng chú ý:

- URL phải là `http(s)`; port hợp lệ; `env_depth >= 1`; pattern/script name không rỗng.
- `probe.preset` thuộc `fingerprint|minimal|none`; trap phải có dạng `holder.name`.
- `press` chỉ nhận `Enter`, `Escape`, `Tab`, `Backspace`.
- Mỗi action bị giới hạn field theo `ALLOWED_FIELDS`; field lạ → lỗi nêu vị trí
  `action script <name>.actions[i]`.
- Template được giữ nguyên lúc load và render khi chạy, vì `save` của action trước cấp biến
  cho `wait_count`/action sau. Thiếu biến → `ValueError` nêu tên biến.

Target mới = thêm `targets/<name>/target.json` + `scripts/*.json`; không sửa Python.

### 3.2 Ports

| Port / DTO | Vị trí |
|---|---|
| `IToolkitPort` | `src/aio_reverse/application/ports/toolkit_port.py:12` |
| `TurnCapture` | `src/aio_reverse/application/ports/browser_session_port.py:11` |
| `IBrowserSessionPort` | `src/aio_reverse/application/ports/browser_session_port.py:23` |
| `StepRecord`, `SessionTurn`, `RunPaths` | `src/aio_reverse/application/ports/web_session_port.py:16,38,57` |
| `IWebSession` | `src/aio_reverse/application/ports/web_session_port.py:64` |
| `IRunStore` | `src/aio_reverse/application/ports/web_session_port.py:121` |
| Export tập trung | `src/aio_reverse/application/ports/__init__.py` |

`IBrowserSessionPort` gồm: `attach`, `list_pages`, `navigate`, `reload`, `evaluate`,
`insert_text`, `click`, `press`, `add_init_script`, `begin_turn`, `end_turn`,
`drain_probe`, `snapshot_env`, `page_info`, `last_network_activity`, `close`.

`IWebSession` gồm: `target`, `open`, `login`, `run_script`, `click`, `type_text`, `press`,
`evaluate`, `navigate`, `inject_probe`, `dump_state`, `close(keep_browser=True)`.

### 3.3 `WreToolkit` adapter

File: `src/aio_reverse/adapters/toolkit/wre_cli.py`

| Nội dung | Dòng |
|---|---|
| Resolve binary: `WRE_BIN` → `target/release/wre` → `target/debug/wre` → `PATH` | 33 |
| `WreToolkit` | 66 |
| `start_browser` (`--start --status`, `--profile`, `--headless` tùy chọn) | 86 |
| `stop_browser` / `browser_status` | 101 / 104 |
| `emit_probe` (flags từ `TargetProbeConfig`, validate `{name, source}`) | 107 |
| `capture` (`--keep-storage --scripts`, `--profile`, timeout `wait_s + 60`) | 154 |
| `env_script` (plain stdout, không `--json`) | 185 |
| `markers` / `pools` / `sweep` / `show` | 199 / 214 / 229 / 246 |
| `_json`: stdout rỗng hoặc JSON hỏng → `ToolkitError` | 266 |
| `_run`: `subprocess.run(..., shell=False)`, luôn `--root <workspace>` | 287 |

`emit_probe` map cờ: `--no-network`, `--workers`, `--no-stealth`, `--no-call-sites`,
`--no-sse`, `--no-websocket`. Kết quả sai shape hoặc sai `name` → `ToolkitError`.

### 3.4 CDP session

Package: `src/aio_reverse/adapters/web/cdp/`

| Module | Trách nhiệm |
|---|---|
| `websocket_transport.py` | Transport sync `websockets` |
| `cdp_channel.py` | Reader thread, pending map, timeout, routing fail loud |
| `page_targets.py` | `/json/list`, `/json/new`, `select_page(exact → prefix → fallback)` |
| `turn_collector.py` | Network request/response/loading, SSE, WebSocket, console, exception |
| `response_bodies.py` | Fetch body cho request khớp pattern, cap 4 MiB, ghi `body_error` |
| `chrome_cdp_session.py` | `ChromeCdpSession` implement `IBrowserSessionPort` |
| `cdp_values.py` | Đọc/validate giá trị CDP dùng chung |

Mốc trong `chrome_cdp_session.py`:

- `attach` (`:64`): chọn page theo origin; fallback page đầu tiên; tắt cache.
- Input tin cậy: `insert_text` (`:158`), `click` (`:161`) qua `Input.dispatchMouseEvent`
  tại tâm `getBoundingClientRect`, `press` (`:217`) qua `Input.dispatchKeyEvent`.
- `add_init_script` (`:246`), `begin_turn` (`:251`), `end_turn` (`:254`).
- `drain_probe` (`:264`): gọi `window.__WRE.drain()`; thiếu probe → `ProbeUnavailableError`.
- `snapshot_env` (`:276`): evaluate JS do `wre env script` sinh.
- `page_info` (`:284`): URL/title/`ready_state`.

Chi tiết hành vi:

- Command timeout: pending được đánh dấu `timed_out`, response đến muộn bị bỏ; response id
  lạ hoặc callback lỗi làm hỏng channel (fail loud).
- `evaluate` raise khi có `exceptionDetails`; phân biệt `undefined` với giá trị JSON.
- Body chỉ fetch cho request khớp `network_patterns`, tối đa 4 MiB.

### 3.5 `ActionEngine` và `ExpressionWaiter`

| Nội dung | Vị trí |
|---|---|
| `ActionEngine.run()` + step records | `src/aio_reverse/application/action_engine.py:24` |
| Thực thi từng action | `src/aio_reverse/application/action_engine.py:70` |
| `ExpressionWaiter` | `src/aio_reverse/application/expression_waiter.py:15` |
| `wait_truthy` / `wait_visible` / `wait_hidden` | `:28` / `:43` / `:52` |
| `count` / `wait_count` / `wait_network_quiet` | `:61` / `:71` / `:86` |

Action `type` click selector trước rồi `insert_text` để đảm bảo input được focus. Mọi
timeout raise `FlowTimeoutError` kèm selector/biểu thức và ngưỡng mong đợi.

### 3.6 `InteractiveSession`

File: `src/aio_reverse/application/interactive_session.py`

| Nội dung | Dòng |
|---|---|
| `InteractiveSession` | 25 |
| `open`: browser profile → attach → navigate → ready → login gate → inject probe | 46 |
| `login`: mở browser, chờ `login_expression`, inject probe | 78 |
| `run_script`: begin → engine → drain → page → env → end | 102 |
| Handover: `click`/`type_text`/`press`/`evaluate`/`navigate` | 129-149 |
| `inject_probe` + verify `window.__WRE.drain` | 151 |
| `dump_state` (page + env) | 169 |
| `close(keep_browser=True)` | 178 |

Thứ tự một lượt đo:

1. `begin_turn()` reset buffer CDP.
2. `ActionEngine.run(script, variables)` chạy action và ghi step.
3. `drain_probe()` lấy snapshot probe **của riêng lượt này**.
4. `page_info()`, `snapshot_env(wre env script)`.
5. `end_turn()` trả `TurnCapture` (network/SSE/WS/console/exception).

Setup script cũng chạy qua `run_script` nhưng use case bỏ `SessionTurn` của chúng, nên
`drain()` vẫn sạch trước lượt đo đầu tiên.

### 3.7 Use case và summary

| Nội dung | Vị trí |
|---|---|
| `RunResult` | `src/aio_reverse/application/use_cases/run_web_scripts.py:22` |
| `RunWebScriptsUseCase.execute` | `src/aio_reverse/application/use_cases/run_web_scripts.py:43` |
| Setup scripts (không ghi artifact) | `src/aio_reverse/application/use_cases/run_web_scripts.py:77` |
| Turn scripts + ghi artifact | `src/aio_reverse/application/use_cases/run_web_scripts.py:82` |
| Lỗi: ghi `run.json` failed rồi re-raise | `src/aio_reverse/application/use_cases/run_web_scripts.py:104` |
| `summarise_turn` / `summarise_run` | `src/aio_reverse/application/turn_summary.py:13,66` |
| Danh sách field probe được đếm | `src/aio_reverse/application/turn_summary.py:11` |

`execute(turn_scripts, setup_scripts=(), variables=None)`:

- từ chối danh sách turn rỗng; preload toàn bộ script trước khi tạo run để lỗi schema
  không để lại thư mục rác;
- mở session một lần;
- chạy setup script, đếm `setup_steps`, không ghi artifact;
- chạy từng turn script, ghi `turn-NN/` và summary từng lượt;
- ghi `summary.json` rồi `run.json` trạng thái `completed`;
- mọi lỗi: ghi `run.json` `status="failed"` + `error` + các turn đã xong, sau đó re-raise;
- `session.close(keep_browser=True)` luôn chạy trong `finally`.

### 3.8 Artifact store

| Nội dung | Vị trí |
|---|---|
| `RunStore` | `src/aio_reverse/infrastructure/artifacts/run_store.py:23` |
| `create_run` (`<UTC>-<target>`) | `:29` |
| `write_run` / `write_summary` | `:36` / `:39` |
| `write_turn` | `:42` |

Layout:

```text
data/output/web/<target>/<run_id>/
├── run.json                  # target, entry_url, port, scripts, variables, status, error
├── summary.json              # totals, per-turn summary, setup_scripts, setup_steps
└── turn-01/
    ├── request.json          # script name + variables
    ├── steps.json            # index, type, selector, result, started_at, ended_at
    ├── probe.json            # snapshot Rust probe (drain)
    ├── network.json          # started_at, ended_at, requests
    ├── sse.json              # metadata SSE event
    ├── websocket.json        # metadata frame in/out
    ├── console.json
    ├── exceptions.json
    ├── env.json              # kết quả eval "wre env script"
    ├── page.json             # url, title, ready_state
    └── timings.json          # duration_s + thời lượng từng step
```

Request record gồm method/URL/status/headers/initiator; body chỉ fetch cho request khớp
`network_patterns`. `data/profiles/` và `data/output/` đều gitignored vì chứa cookie,
prompt và body thật.

### 3.9 CLI, composition và entrypoint

| Nội dung | Vị trí |
|---|---|
| Wiring dùng chung CLI + MCP | `src/aio_reverse/composition.py:15-45` |
| Parser `web` / `mcp` | `src/aio_reverse/main.py:27` |
| Không tham số = MCP | `src/aio_reverse/main.py:51` |
| `web targets` / `web scripts` | `src/aio_reverse/cli/web_targets.py:24,37` |
| `web probe` (in JS probe) | `src/aio_reverse/cli/web_probe.py:22` |
| `web login` | `src/aio_reverse/cli/web_login.py:30` |
| `web run` (`--script` lặp, `--var NAME=VALUE`) | `src/aio_reverse/cli/web_run.py:52` |
| `web session/state/click/type/press/evaluate/navigate` | `src/aio_reverse/cli/web_handover.py:64-111` |

Lỗi `AioReverseError`, `ValueError`, `FileNotFoundError` được in `error: ...` ra stderr
và trả exit code 2. `web run` mặc định dùng `target.turn_scripts` nếu không có `--script`.

### 3.10 MCP server

| Nội dung | Vị trí |
|---|---|
| `SessionRegistry` (một phiên/target, `close_all`) | `src/aio_reverse/adapters/mcp/session_registry.py:14` |
| `WebToolServices` | `src/aio_reverse/adapters/mcp/web_tools.py:20` |
| Đăng ký 11 tool | `src/aio_reverse/adapters/mcp/web_tools.py:111` |
| `WebMcpServer.run` + cleanup `finally` | `src/aio_reverse/adapters/mcp/server.py:34-44` |
| `build_server` | `src/aio_reverse/adapters/mcp/server.py:47` |

11 tool: `web_targets`, `web_open`, `web_run_script`, `web_state`, `web_inject_probe`,
`web_click`, `web_type`, `web_press`, `web_evaluate`, `web_navigate`, `web_close`.

- Server dùng `mcp.server.mcpserver.MCPServer` (MCP 2.x; `FastMCP` đã đổi tên).
- Chỉ chạy stdio cục bộ; `web_evaluate`/`web_navigate` là bề mặt nguy hiểm, không expose
  ra mạng.
- `web_close` mặc định `keep_browser=true`, giữ Chrome và profile cho lần sau.

### 3.11 Hạ tầng, lỗi, dependency, gitignore

| Nội dung | Vị trí |
|---|---|
| `AppConfig.targets_root` (`targets/`) | `src/aio_reverse/infrastructure/config.py:37` |
| `AppConfig.profiles_dir` / `profile_dir` (`data/profiles/<target>`) | `:41` / `:44` |
| `AppConfig.web_output_dir` (`data/output/web`) | `:66` |
| `ensure_directories` | `:75` |
| `ToolkitError` / `ToolkitNotFoundError` | `src/aio_reverse/domain/errors.py:28,47` |
| `BrowserSessionError` | `src/aio_reverse/domain/errors.py:51` |
| `AuthenticationRequiredError` | `:55` |
| `FlowTimeoutError` | `:59` |
| `ProbeUnavailableError` | `:63` |
| `ActionScriptError` | `:67` |
| `websockets>=13.0`, `mcp` | `pyproject.toml` |
| Ignore `data/workspace/`, `data/profiles/`, `data/output/` | `.gitignore:22-24` |

### 3.12 Tests

| File | Số test | Phạm vi |
|---|---|---|
| `tests/test_web_target.py` | 11 | target schema, loader strict, registry |
| `tests/test_action_script.py` | 29 | 11 action type, template/save, lỗi schema |
| `tests/test_wre_cli.py` | 15 | argv, JSON, lỗi CLI, `--profile`, `probe emit` |
| `tests/test_cdp_routing.py` | 29 | channel routing/timeout, `select_page`, collector, body cap, click visible |
| `tests/test_action_engine.py` | 5 | step records, save, timeout, lỗi action |
| `tests/test_interactive_session.py` | 8 | open/login, probe inject, thứ tự drain, handover |
| `tests/test_run_web_scripts.py` | 5 | setup/turn, artifact, lỗi, close |
| `tests/test_mcp_tools.py` | 11 | session registry, 11 tool, run/handover/close |
| `tests/test_page_element_expressions.py` | 3 | count/presence/absence/click chỉ xét phần tử render |
| **Tổng** | **116** | không cần Chrome/wre thật |

Fixture CLI giả: `tests/fixtures/fake_wre.py` (hỗ trợ `probe emit`, `--profile`).

Rust:

| Lệnh | Kết quả |
|---|---|
| `cargo test -p wre-probe` | 15 pass (5 unit + 10 V8) |
| `cargo test -p wre-target -p wre-cli` | 9 pass |
| `cargo test -p wre-env` | 12 pass (4 unit + 8 realm) |

## 4. Luồng chạy end-to-end

1. `aio-reverse web run chatgpt --script send_prompt --var prompt="..."`
2. `composition.build_*` tạo config, registry, toolkit, store, session.
3. `RunWebScriptsUseCase.execute` tạo `run_id = <UTC>-<target>` và thư mục run.
4. `InteractiveSession.open()`:
   - `wre browser --start --status --profile data/profiles/chatgpt`;
   - attach page theo origin (fallback page đầu tiên);
   - navigate `entry_url` nếu URL hiện tại khác origin;
   - chờ `ready_expression`;
   - kiểm tra `login_expression`; false → `AuthenticationRequiredError`
     (gợi ý `aio-reverse web login chatgpt`);
   - `wre probe emit` → `add_init_script` + evaluate → verify `window.__WRE.drain`.
5. Setup scripts (ví dụ `new_chat`) chạy, `drain_probe()` bỏ dữ liệu setup.
6. Mỗi turn script:
   - `begin_turn()`;
   - action: count/save → type → click → wait_count → wait_hidden → wait_network_quiet;
   - `drain_probe()` (chỉ dữ liệu lượt này);
   - page info + env snapshot; `end_turn()`;
   - `RunStore.write_turn`.
7. `summary.json`, `run.json` (`completed`); `session.close(keep_browser=True)`.
8. Chrome và profile vẫn sống; agent có thể tiếp tục bằng `web state/click/type/...`
   hoặc MCP tool mà không đăng nhập lại.

## 5. Kiểm chứng

### 5.1 Unit tests

```bash
uv run python -m unittest discover -s tests -v
```

Kết quả hiện tại: **116 test pass** trong 0.299s, không cần Chrome hay binary `wre` thật.

### 5.2 Rust tests và probe JS

```bash
cd libs/web-re-toolkit
cargo test -p wre-probe -p wre-target -p wre-cli -p wre-env
cargo build --release -p wre-cli
./target/release/wre --json probe emit --preset fingerprint \
  --property navigator.userAgent --property navigator.webdriver > /tmp/probe.json
```

- `wre-probe`: 15 pass; `wre-target` + `wre-cli`: 9 pass; `wre-env`: 12 pass.
- `probe emit`: trả `{name, source, bytes}`; source đã qua `node --check`.
- Ba case lỗi (preset sai, trap thiếu `.`, `--target` xung đột flag) exit 1 với thông điệp
  rõ ràng (đã verify ở Phase 2).

### 5.3 E2E fakechat (đã chạy)

Kịch bản: `tests/fixtures/fake_chat_server.py` phục vụ trang chat tại
`http://127.0.0.1:8765/`, target `targets/fakechat/`, Chrome port 9565, profile
`data/profiles/fakechat`.

```bash
uv run python tests/fixtures/fake_chat_server.py --port 8765 &
uv run aio-reverse web login fakechat
uv run aio-reverse web run fakechat --script send_prompt --script send_prompt \
  --var prompt="phase8 ping"
```

Kết quả run `20261025T063735Z-fakechat`:

| Kiểm tra | Lượt 1 | Lượt 2 |
|---|---|---|
| CDP requests | `conversation?turn=1`, `stream?turn=1` | `conversation?turn=2`, `stream?turn=2` |
| CDP SSE / WS | 3 event / 2 frame | 3 event / 2 frame |
| Probe `network` | 1 (URL `turn=1`) | 1 (URL `turn=2`) |
| Probe `sse` | 1 record, 3 message, done | 1 record, 3 message, done |
| Probe `websocket` | 1 record, 2 frame, done | 1 record, 2 frame, done |
| Probe `reads` / `calls` | 2 / 2 | 2 / 2 (không cộng dồn) |

Lượt 2 chỉ chứa dữ liệu lượt 2 ở cả CDP và probe, chứng minh `drain()` reset đúng.
Artifact đầy đủ 12 file mỗi lượt dưới
`data/output/web/fakechat/20261025T063735Z-fakechat/`.

MCP smoke (stdio thật, cùng Chrome đang sống):

- `tools/list` trả đúng 11 tool.
- `web_open` → `web_run_script` (`send_prompt`, 1 lượt, probe có đủ
  reads/calls/network/sse/websocket) → `web_state` → `web_close`
  (`closed=true`, Chrome được giữ chạy).

### 5.4 E2E ChatGPT thật (đã chạy)

Điều kiện: người dùng đăng nhập tay một lần trong Chrome profile
`data/profiles/chatgpt`. Không có credential tự động hóa.

```bash
uv run aio-reverse web login chatgpt
uv run aio-reverse web run chatgpt --script send_prompt --var prompt="ping"
```

Kết quả run cuối `20261025T115909Z-chatgpt`:

| Kiểm tra | Kết quả |
|---|---|
| Setup + turn steps | 3 setup + 6/6 action (`count`=0, `type`, `click`, `wait_count`, `wait_hidden`, `wait_network_quiet`) |
| CDP requests | 26 request, 17 khớp pattern hội thoại/`backend-api` |
| Probe | reads 18, calls 11, events 82, network 17, websocket 1, sse 0 |
| SSE/WebSocket | ChatGPT stream bằng `fetch`, không dùng `EventSource`; probe bắt 1 WSS mới (frames in/out, không payload) |
| CDP WebSocket frames | 7 |
| Console errors / exceptions | 0 / 0 |
| Trang kết thúc | hội thoại mới, `readyState=complete` |

Run trước đó (`20261025T115728Z-chatgpt`) có 13 unhandled rejection phát sinh từ
env capture; đã sửa và xác nhận 0 exception ở run cuối (xem mục 6).

Profile bền: dừng Chrome rồi chạy `web state chatgpt` không cần login lại. Lần mở
nguội đầu tiên có thể kẹt `readyState=interactive` do SPA chưa hydrate; một lần
reload trang là hồi phục. Đây là rủi ro của trang đích, không phải lỗi auth.

Selector đã xác nhận trên DOM thật (2026-10-25):

- Composer: `form[data-chatgpt-composer] div.ProseMirror[contenteditable="true"]`
- Send: `form[data-chatgpt-composer] button[aria-label="Send"]`
- Stop stream: `button[aria-label="Stop"]`
- New chat: `button[aria-label="New chat"]`
- Assistant message: `h4[data-conversation-role="assistant"]`
- Đăng nhập: `button[aria-label="Open profile menu"]`

ChatGPT giữ DOM của route cũ trong workspace `display:none`; vì vậy primitive
`click`/`count`/`wait_*` chỉ xét phần tử đang render (có kích thước và không
`visibility:hidden`).

## 6. Bài học thực nghiệm giữ lại từ kiến trúc cũ

Các phát hiện dưới đây vẫn đúng và định hình kiến trúc hiện tại:

1. **`__WRE` là session-scoped.** `wre capture` cài probe bằng
   `Page.addScriptToEvaluateOnNewDocument`, nhưng đăng ký mất khi process capture thoát.
   Đây là lý do kiến trúc cũ phải dùng probe Python tạm thời.
   **Kiến trúc mới giải quyết bằng `wre probe emit`:** Python lấy JS từ Rust rồi tự
   `add_init_script` + evaluate trong chính phiên CDP đang sống, nên probe tồn tại suốt
   phiên và không cần `wre capture` trên đường chạy chính.
2. **`wre capture` kết thúc ở `about:blank`** (không đóng page). `select_page` vẫn giữ
   fallback page đầu tiên để tránh tích tụ tab.
3. **`wre browser --start` im lặng nếu Chrome đã chạy.** Vì vậy
   `WreToolkit.start_browser` luôn thêm `--status` để có JSON trong cả hai trường hợp.
4. **Input phải tin cậy.** `element.click()` tạo `isTrusted=false`; adapter dùng
   `Input.dispatchMouseEvent` tại tâm element và `Input.insertText` cho text.
5. **`wre env snapshot` navigate**, làm mất trạng thái chat; chỉ dùng `wre env script`
   + evaluate (`snapshot_env`) giữa phiên.
6. **SPA giữ DOM của route cũ.** ChatGPT để tin nhắn cũ trong workspace
   `display:none`; `querySelectorAll` toàn cục vẫn đếm chúng. Vì vậy `click`,
   `count`, `wait_visible`, `wait_hidden`, `wait_count` phải lọc theo kích thước
   render (`page_element_expressions.py`), nếu không script sẽ click/đếm nhầm bản
   cache ẩn.
7. **Gọi getter có thể tạo promise.** `ReadableStreamDefaultReader.closed` trả
   promise; env capture cũ bỏ qua nó nên khi stream đóng, promise reject thành
   unhandled rejection trong trang (13 lần ở run ChatGPT đầu). `CAPTURE` giờ gắn
   rejection handler cho mọi getter trả thenable.

## 7. Kiến trúc cũ đã bị thay thế

| Thành phần cũ (đã xóa) | Thay bằng |
|---|---|
| `targets/base.py` (`ProbeMode`, `TurnSpec`, `WebPageSpec`, `WebTargetSpec`) | `targets/web_target.py` + `targets/<name>/target.json` |
| `targets/chatgpt.py` (hardcode selector) | `targets/chatgpt/target.json` + `scripts/*.json` |
| `FlowRunner` (`adapters/web/flow_runner.py`) | `application/interactive_session.py` + `action_engine.py` |
| `CHAT_PROBE_JS` (~270 dòng Python) | `wre probe emit` (Rust) |
| `dump_wre` / `dump_python_probe` | `drain_probe()` duy nhất |
| `IWebFlowRunner`, `FlowPreparation`, `FlowTurn` | `IWebSession`, `SessionTurn` |
| `RunWebFlowUseCase` / `run_web_flow.py` | `RunWebScriptsUseCase` / `run_web_scripts.py` |
| `experiments/chatgpt.py` (`--prompt`, `--login-only`) | `aio-reverse web login/run/...` |
| MCP skeleton `adapters/mcp/tools.py` | `adapters/mcp/{server,session_registry,web_tools}.py` |
| Profile tạm `data/workspace/chrome-profiles/profile-<port>` | Profile bền `data/profiles/<target>/` |

Xác nhận sạch:

```bash
rg "ProbeMode|TurnSpec|CHAT_PROBE_JS|dump_wre|dump_python_probe|probe-python|FlowRunner|RunWebFlowUseCase|web_flow_port|flow_runner|targets\.base|targets\.chatgpt" src tests
```

Kết quả mong đợi: không khớp.

## 8. Cách chạy và checklist review

```bash
# 1. Build backend một lần (target/ đã gitignore)
cd libs/web-re-toolkit
cargo build --release -p wre-cli
./target/release/wre --version
cd ../..

# 2. Cài dependency Python
uv sync

# 3. Unit tests
uv run python -m unittest discover -s tests -v

# 4. Khám phá target/script
uv run aio-reverse web targets
uv run aio-reverse web scripts chatgpt

# 5. Đăng nhập thủ công một lần; Chrome ở lại port 9445
uv run aio-reverse web login chatgpt

# 6. Một lượt đo
uv run aio-reverse web run chatgpt --script send_prompt --var prompt="ping"

# 7. Handover trên phiên đang sống
uv run aio-reverse web state chatgpt
uv run aio-reverse web click chatgpt 'form[data-chatgpt-composer] div.ProseMirror[contenteditable="true"]'
uv run aio-reverse web type chatgpt "follow-up"
uv run aio-reverse web press chatgpt Enter

# 8. MCP (stdio)
uv run aio-reverse            # hoặc: uv run aio-reverse mcp
```

Checklist review:

1. `git status --short` — thay đổi đang ở working tree, chưa commit.
2. Đọc theo thứ tự: `target.json` → `targets/*` → ports → toolkit → CDP package →
   action engine → interactive session → turn summary → use case → store → CLI/MCP.
3. Đối chiếu artifact thật dưới `data/output/web/chatgpt/<run_id>/` sau lần chạy đầu.
4. Xem `summary.json` để biết request hội thoại/SSE/WS và prompt có xuất hiện trong body.
5. Nếu `window.__WRE` thiếu sau navigate: kiểm tra `wre probe emit`, init script và CSP.

## 9. Việc còn lại và giới hạn

Việc còn lại:

1. **Phase B marker sweep:** `markers` → `pools` → baseline → từng pool (tab mới,
   `PUT /json/new`) → `sweep` → `findings.json`.
2. **ChatGPT DOM có thể đổi:** selector đã xác nhận 2026-10-25; khi fail, dùng
   `web state`/`web evaluate` dò lại và cập nhật `targets/chatgpt/`.
3. **Cold start SPA:** nếu `ready_expression` timeout ngay sau khi Chrome được
   khởi động lại, reload trang rồi chạy lại lệnh; profile vẫn giữ đăng nhập.

Giới hạn/trade-off:

- `wre capture` static capture có trong `WreToolkit` nhưng **không** nằm trên đường chạy
  `web run`; nếu dùng phải chạy profile/port riêng để tránh xung đột Chrome đang mở.
- SSE/WebSocket trong probe chỉ ghi metadata (số message/frame, bytes, state, site);
  payload đi qua CDP Network events.
- `env.json` khá lớn (khoảng 1.3 MB/lượt ở `env_depth=4`); giảm depth khi chạy dài.
- `wre sweep` là offline; runner phải tự chụp payload cho từng arm.
- Chưa ghi DB; artifact JSON là source of truth.
- Chỉ dùng tài khoản tự sở hữu/được phép; tôn trọng ToS và rate limit; không tự động hóa
  credential.
