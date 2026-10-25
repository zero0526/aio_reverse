# AIO-Reverse — Kế hoạch & theo dõi tiến độ

> Cập nhật lần cuối: 2026-10-25 (working tree, chưa commit)

## 0. Cách dùng file này

- `[ ]` chưa làm, `[x]` đã làm **và đã verify**, task đang làm ghi thêm `(đang làm)`.
- Chỉ tick checkbox sau khi lệnh verify của task/phase chạy pass.
- Mỗi phase xong: thêm một dòng vào mục 8 (ngày, phase, lệnh verify, kết quả).
- Nếu phải đổi thiết kế so với kế hoạch: thêm dòng "Sai lệch" trong mục 8 kèm lý do thực nghiệm; không sửa lịch sử cũ.
- Không ghi cookie, token, body hay prompt thật vào file này; chỉ mô tả schema.

## 1. Mục tiêu & phạm vi đã chốt

Chuyển toàn bộ phần nặng xuống Rust engine, Python chỉ còn là lớp wrapper mỏng:

| Hạng mục | Chốt |
|---|---|
| Probe trong trang | Rust sở hữu duy nhất, Python lấy qua `wre probe emit` |
| Điều khiển phiên | Python giữ Chrome sống, agent handover qua API + CLI + MCP |
| Cấu hình mục tiêu | JSON tại repo-root `targets/<name>/target.json` + `scripts/*.json` |
| Hành vi từng lượt | Action script JSON, không hardcode `TurnSpec` trong Python |
| Đăng nhập | Human-in-the-loop một lần, profile bền tại `data/profiles/<target>/` |
| Rust scope | `wre probe emit`, hook SSE/WebSocket, `drain()`, `--profile` cho browser/capture |
| Agent handover | API Python + CLI + MCP (FastMCP, session registry sống lâu) |

Ngoài phạm vi: PyO3/in-process Rust, tự động đăng nhập, Phase B marker sweep.

## 2. Kiến trúc đích

```text
Agent / người dùng
   │  (MCP stdio)                     (CLI)
   ▼                                    ▼
adapters/mcp/web_tools.py          cli/web_*.py
   └──────────┬──────────────────────────┘
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

Nguyên tắc:

1. Một nguồn probe duy nhất là Rust; Python inject bằng init script + evaluate ngay, và `drain()` mỗi lượt.
2. Mỗi lượt là action script JSON; target mới chỉ cần thêm thư mục `targets/<name>/`, không sửa code.
3. Không còn `ProbeMode`, `TurnSpec`, `CHAT_PROBE_JS`.
4. Session Chrome và CDP sống lâu, không đóng sau mỗi lượt; đóng process không làm mất đăng nhập.

## 3. Trạng thái tổng quan

| Phase | Nội dung | Trạng thái | Verify chính |
|---|---|---|---|
| 0 | Tài liệu theo dõi (`docs/plans.md`) | xong | đọc lại file, `git diff --stat` |
| 1 | Rust probe: SSE/WebSocket + `drain()` | xong | `cargo test -p wre-probe` (15 pass) |
| 2 | Rust CLI: `probe emit` + `--profile` | xong | `cargo test -p wre-target -p wre-cli` (9 pass) + build release + emit JS syntax OK |
| 3 | Python target.json + action script | xong | `python -m unittest tests.test_web_target tests.test_action_script` (40 pass) |
| 4 | Tách CDP adapter + `drain_probe` | xong | `python -m unittest tests.test_cdp_routing` (28 pass) + full suite 108 pass |
| 5 | ActionEngine + InteractiveSession + artifact + CLI | xong | full suite 129 pass + `web targets/scripts/probe` + `node --check` |
| 6 | FastMCP + session registry | xong | full suite 140 pass + stdio `tools/list` (11 tool) + `web_targets` |
| 7 | Dọn symbol cũ + cập nhật docs | xong | `rg` sạch + full suite 112 pass |
| 8 | Kiểm chứng E2E | xong | fakechat 2 lượt + MCP smoke + `chatgpt.com` thật (0 exception) + profile bền qua restart |
| 9 | Skill catalog + báo cáo hành vi ChatGPT (`docs/skills/`) | xong | `docs/skills` đủ SKILL/references/templates/examples; JSON template parse; link nội bộ resolve; full suite 116 pass |
| 9b | Crate `wre-template` + CLI `template diff` | xong (trước phiên này) | `cargo test -p wre-template` (10 pass) + clippy + CLI smoke |
| 10 | An toàn artifact + deadline action script | xong | 134 test + replay ChatGPT sạch body/stream |
| 11 | Tích hợp `wre-template`: snapshot + skeleton | xong | 159 test + `cargo test -p wre-template -p wre-cli` (15 pass) + replay ChatGPT: 2 snapshot → skeleton reduction 0.9631, 6 slot, MCP 13 tool |
| 12 | Replay matrix + tài liệu | xong | policy scan run mới (0 body/0 header lộ/WS metadata) + MCP stdio smoke 13 tool + docs/skills cập nhật + link checker sạch |
| 11 | Tích hợp `wre-template`: snapshot HTML + skeleton | chưa làm | Rust test/build + Python suite + replay fakechat |
| 12 | Replay matrix + cập nhật skill docs | chưa làm | fakechat 2 lượt + MCP 13 tool + ChatGPT thật |

## 4. Roadmap chi tiết

### Phase 1 — Rust probe: SSE/WebSocket + `drain()`

Files: `libs/web-re-toolkit/crates/wre-probe/src/lib.rs`, `.../src/runtime.rs`, `.../tests/runs_in_v8.rs`.

- [x] `SurfaceSpec` thêm `sse`/`websocket` (`default_true`), `Default`, `merge()`, `config()`
- [x] `ProbeDump` thêm `sse`/`websocket` + `parse()`
- [x] Giữ native `EventTarget.prototype.addEventListener` trước khi trap
- [x] Hook `EventSource`: message count, bytes, state, site, url (không ghi payload)
- [x] Hook `WebSocket`: frames in/out, bytes, close code/reason, error
- [x] `snapshot()` dùng chung cho `dump()`; thêm `drain()`; `reset()` xóa cả stream
- [x] V8 test: record stream, stealth `toString`, drain rồi dump rỗng
- [x] `cargo test -p wre-probe` pass (5 unit + 10 V8)

### Phase 2 — Rust CLI: `wre probe emit` + `--profile`

Files: `crates/wre-cli/src/args.rs`, `main.rs`, `probe_cmd.rs` (mới), `capture_cmd.rs`, `crates/wre-target/src/lib.rs`, `targets/example.toml`.

- [x] Top-level `Probe(ProbeCommand)` với `Emit`
- [x] Flags: `--target`, `--name`, `--preset`, `--property`, `--method`, `--event`, `--no-network`, `--workers`, `--no-stealth`, `--no-call-sites`, `--no-sse`, `--no-websocket`
- [x] `--target` conflict với flag khác → lỗi; preset sai → lỗi; trap thiếu dấu `.` → lỗi
- [x] Output JSON `{name, source, bytes}`; plain in JS thô
- [x] `wre-target::Probe` thêm `sse`/`websocket` + `to_spec()`
- [x] `Browser`/`Capture` thêm `--profile`; tạo profile dir trước khi launch
- [x] `cargo test -p wre-target -p wre-cli` pass (9 test)
- [x] `cargo build --release -p wre-cli` + `probe emit` pass `node --check` + 3 case lỗi fail loud

### Phase 3 — Python target + action script

Files: `targets/chatgpt/{target.json,scripts/new_chat.json,scripts/send_prompt.json,README.md}`, `src/aio_reverse/targets/{web_target,target_loader,target_registry,action_script,action_script_loader}.py`.

- [x] `WebTargetSpec` + `TargetProbeConfig`, validate fail-loud (bỏ `ProbeMode`/`TurnSpec`/`WebPageSpec`)
- [x] `target_loader.py`: JSON strict, unknown key → lỗi, resolve script path
- [x] `target_registry.py`: quét `PROJECT_ROOT/targets/*/target.json`
- [x] `action_script.py`: 11 action type + validate field/whitelist `press`
- [x] `action_script_loader.py`: template `{{var}}` — loader giữ template, `required_variables()` liệt kê biến ngoài, `resolve_action()` render khi chạy và lỗi nêu tên biến thiếu
- [x] `config.py`: `targets_root`, `profiles_dir`, `profile_dir(target)`
- [x] `.gitignore`: thêm `data/profiles/`
- [x] `targets/chatgpt/` JSON + ghi chú selector chưa xác nhận
- [x] Tests `test_web_target.py`, `test_action_script.py` pass (40 test)

### Phase 4 — Tách CDP adapter + probe hợp nhất

Files: `src/aio_reverse/adapters/web/cdp/{websocket_transport,cdp_channel,page_targets,turn_collector,response_bodies,chrome_cdp_session}.py`, `application/ports/browser_session_port.py`.

- [x] Tách 6 module, giữ nguyên hành vi Network/SSE/WS/console/exception (+ `cdp_values.py` dùng chung)
- [x] `dump_wre` + `dump_python_probe` → một `drain_probe()` gọi `window.__WRE.drain()`; thiếu probe → `ProbeUnavailableError`
- [x] Thêm `navigate(url)` (đã có) và `list_pages()`
- [x] Cập nhật `IBrowserSessionPort` (bỏ dump phân mảnh, thêm `drain_probe`/`list_pages`)
- [x] `press()` hỗ trợ `Enter/Escape/Tab/Backspace` (text key dùng `keyDown`, còn lại `rawKeyDown`)
- [x] `tests/test_cdp_routing.py` chuyển import + test drain/list/press pass (28 test)
- [x] Full suite pass (108 test)

### Phase 5 — ActionEngine + InteractiveSession + artifact + CLI

Files: `application/{action_engine,interactive_session,expression_waiter}.py`, `application/ports/web_session_port.py`, `application/use_cases/run_web_scripts.py`, `infrastructure/artifacts/run_store.py`, `adapters/toolkit/wre_cli.py`, `cli/{common,web_login,web_run,web_handover,web_targets}.py`, `main.py`, `application/ports/toolkit_port.py`.

- [x] `ActionEngine.run()` + step records + `ActionScriptError`
- [x] `InteractiveSession.open()` inject probe + verify `__WRE`
- [x] `InteractiveSession.run_script()` begin/drain/end đúng thứ tự
- [x] Handover: click/type/press/evaluate/navigate/inject_probe/dump_state/close
- [x] `run_web_scripts` use case + login gate + ghi run failed rồi re-raise
- [x] Artifact layout mới (`turn-NN/probe.json`, `sse.json`, `websocket.json`, ...)
- [x] `WreToolkit.emit_probe/start_browser(profile)/capture(profile)` + port
- [x] CLI `web targets|login|scripts|run|session|state|probe|click|type|press|evaluate|navigate`, `mcp`; không tham số = `mcp` (wiring tách theo lệnh, không dùng file tên chung như `common.py`)
- [x] Tests `test_action_engine.py`, `test_interactive_session.py`, `test_run_web_scripts.py` pass
- [x] `tests/fixtures/fake_wre.py` hỗ trợ `probe emit` + `--profile`

### Phase 6 — MCP FastMCP + session registry

Files: `adapters/mcp/{server,session_registry,web_tools}.py`.

- [x] `SessionRegistry` (one session/target, khóa mở trùng, `close_all`)
- [x] 11 tool web (`web_targets`, `web_open`, `web_run_script`, `web_state`, `web_inject_probe`, `web_click`, `web_type`, `web_press`, `web_evaluate`, `web_navigate`, `web_close`)
- [x] `server.py` dùng `FastMCP("aio-reverse")`, stdio, cleanup `finally`
- [x] Xóa `adapters/mcp/tools.py`; test `test_mcp_tools.py` pass
- [x] Smoke `tools/list` qua stdio

### Phase 7 — Dọn dẹp + tài liệu

- [x] Xóa `flow_runner.py`, `web_flow_port.py`, `run_web_flow.py`, `targets/base.py`, `targets/chatgpt.py`, `experiments/chatgpt.py`, `adapters/mcp/tools.py` (kèm `legacy_run_store.py` và test cũ)
- [x] Thêm `ActionScriptError` vào `domain/errors.py`
- [x] Cập nhật `__init__.py` ports/use_cases/adapters web
- [x] `rg "ProbeMode|TurnSpec|CHAT_PROBE_JS|dump_wre|dump_python_probe|probe-python" src tests` rỗng
- [x] `README.md`: quickstart mới + cảnh báo tài khoản được phép/ToS
- [x] `docs/capture_analystic.md`: kiến trúc mới, đánh dấu phần cũ "đã thay thế"
- [x] Full test suite pass

### Phase 8 — Kiểm chứng E2E

- [x] `web probe chatgpt > /tmp/probe.js && node --check /tmp/probe.js`
- [x] Trang chat giả (`tests/fixtures/fake_chat_server.py`) có textarea/send/reply/SSE/WebSocket
- [x] `web run` 2 lượt: `probe.json` có reads/calls/network/sse/websocket
- [x] Lượt 2 chỉ chứa dữ liệu lượt 2 (chứng minh `drain()`)
- [x] ChatGPT thật: `web login` (tay) → `web run`; dừng/mở lại Chrome rồi `web state` không cần login lại
- [x] MCP smoke `web_open → web_run_script → web_state → web_close`
- [x] Ghi kết quả vào mục 8

### Phase 9 — Skill catalog + báo cáo hành vi ChatGPT

Bổ sung theo yêu cầu người dùng ngày 2026-10-25. Phạm vi: **chỉ tài liệu**, không sửa code.

- [x] `docs/skills/SKILL.md` — quy trình 7 cổng, non-negotiables, bảng lệnh, code gate
- [x] `references/01..09` — quyền/phạm vi, target config, DOM map, action chain, network/stream,
  artifact forensics, behavior report, failure playbook, command map
- [x] `templates/{behavior-report.md,target.json,action-script.json}`
- [x] `examples/chatgpt/{behavior-report,dom-map,network-map,action-chain,lessons}.md`
- [x] Báo cáo hành vi ChatGPT dựa trên run thật `20261025T115909Z-chatgpt`, không có body/token/ID
- [x] Ghi nhận 3 gap phát hiện khi đối chiếu code: `network_patterns` vừa lọc summary vừa bật
  response-body capture; `ActionScript.timeout_s` chưa được engine enforce; CDP
  `sse.json`/`websocket.json` có payload dù probe chỉ ghi metadata
- [x] Verify: JSON template parse; link nội bộ resolve; `SKILL.md` < 500 dòng; full suite pass

### Phase 10 — An toàn artifact + deadline action script

Bổ sung sau Phase 9 để đóng 3 gap và tránh sinh artifact HTML khi chưa có policy.

- [x] `ActionEngine` enforce `ActionScript.timeout_s` (deadline tổng + cap timeout từng action)
- [x] `WebTargetSpec` + loader: `body_capture_patterns` (mặc định rỗng), tách khỏi `network_patterns`
- [x] `ChromeCdpSession`/`response_bodies` chỉ fetch body theo `body_capture_patterns`
- [x] Redact header nhạy cảm (`cookie`, `set-cookie`, `authorization`, `proxy-authorization`)
- [x] Request body mặc định chỉ lưu `request_body_bytes` + `request_body_sha256`
- [x] Probe `network[].body` sample cũng theo policy (null + `body_redacted` nếu URL không khớp)
- [x] `WebTargetSpec` + loader: `stream_payloads` (mặc định false)
- [x] SSE/WS mặc định chỉ lưu `*_bytes` + `*_sha256`; raw khi bật cờ
- [x] `targets/{chatgpt,fakechat}/target.json` cập nhật key mới
- [x] Test deadline (2), body capture (2), redaction (3), stream policy (2)
- [x] Full suite pass + replay ChatGPT không lộ body/cookie/payload ngoài cờ

### Phase 11 — Tích hợp `wre-template`

- [x] `wre --json template diff` trả object `{pages, first_page, reduction_ratio, skeleton, slots}`; `--slots` giữ mảng
- [x] `IToolkitPort`/`WreToolkit.template_diff(pages, xpath)` validate kết quả fail loud
- [x] `IBrowserSessionPort.outer_html()` + giới hạn 8 MiB
- [x] `artifact_naming.py` dùng chung `safe_name`/`utc_stamp`
- [x] `HtmlSnapshotStore` ghi `data/output/web/<target>/snapshots/<utc>-<label>.html`, không ghi đè
- [x] `AppConfig.html_snapshots_dir(target)`
- [x] `PageSnapshot` + `IWebSession.capture_page` + `CapturePageSnapshotUseCase`
- [x] `AnalyzeTemplateUseCase` validate ≥ 2 file `.html`
- [x] CLI `web snapshot`, `web skeleton`; MCP `web_snapshot`, `web_skeleton` (13 tool)
- [x] Test toolkit/session/store/use case/MCP + fixture HTML + fake_wre
- [x] Rust test/build, Python full suite (159 OK), replay snapshot/skeleton **ChatGPT thật** (theo chỉ đạo bỏ fakechat): `20261025T142753Z-home.html` + `20261025T150041Z-thread.html` → skeleton 96.3% reduction, 6 slot

### Phase 12 — Replay matrix + tài liệu

- [x] ~~fakechat: 2 lượt + snapshot~~ → theo chỉ đạo người dùng, matrix chạy trên
  **ChatGPT thật**; đường fakechat vẫn được coverage bởi 159 unit/integration test
  (store, use case, toolkit argv, MCP 13 tool)
- [x] Kiểm tra policy artifact trên run mới (`20261025T133736Z-chatgpt/turn-01`):
  18 network entry — 0 raw body, 0 sensitive header chưa redact; WS 2 event chỉ
  `*_bytes`/`*_sha256` (stream_payloads=false); probe 12 sample — 0 body
- [x] MCP smoke stdio 13 tool: initialize → `web_targets` (field mới
  `body_capture_patterns`/`stream_payloads`) → `web_state` attach trang thread thật →
  `web_snapshot` (816.802 B) → `web_skeleton` (reduction 0.9631, 6 slot) →
  `web_close` giữ Chrome. Không gọi `web_run_script` qua MCP để tránh thêm lượt gửi thật
- [x] ChatGPT thật: snapshot home/thread + skeleton 96.3% (xem
  `report_template_integration_20261025.md` mục 4; `send_prompt` fail "Failed to fetch"
  4 lần, Retry 1 lần trên nút của trang → thread hoàn tất, không spam)
- [x] Cập nhật `docs/skills/{SKILL.md,references/03,09,10}`: gate 2 skeleton-first
  (Bước 1b), 2 lệnh CLI + 2 MCP tool + bảng ngữ nghĩa phiên, JSON shape mới của
  `wre --json template diff`; `templates/target.json` + references 05/06 đã làm ở Phase 10
- [x] Ghi chú schema Phase 10 ở cuối `examples/chatgpt/network-map.md` (làm tại Phase 10)
- [x] Báo cáo `docs/report_artifact_safety_20261025.md`,
  `docs/report_template_integration_20261025.md`, `docs/report_replay_matrix_20261025.md`

## 5. Bảng task → file chính → verify

| Task | File chính | Verify |
|---|---|---|
| Stream probe | `libs/web-re-toolkit/crates/wre-probe/src/runtime.rs` | `cargo test -p wre-probe` |
| Probe spec | `libs/web-re-toolkit/crates/wre-probe/src/lib.rs` | `cargo test -p wre-probe` |
| CLI emit | `libs/web-re-toolkit/crates/wre-cli/src/probe_cmd.rs` | `wre --json probe emit ...` |
| CLI profile | `libs/web-re-toolkit/crates/wre-cli/src/capture_cmd.rs` | `wre browser --start --profile /tmp/x` |
| Target schema | `src/aio_reverse/targets/web_target.py` | `tests/test_web_target.py` |
| Action schema | `src/aio_reverse/targets/action_script.py` | `tests/test_action_script.py` |
| CDP package | `src/aio_reverse/adapters/web/cdp/*.py` | `tests/test_cdp_routing.py` |
| Action engine | `src/aio_reverse/application/action_engine.py` | `tests/test_action_engine.py` |
| Element render filter | `src/aio_reverse/application/page_element_expressions.py` | `tests/test_page_element_expressions.py` + `tests/test_cdp_routing.py` |
| Env capture promise safety | `libs/web-re-toolkit/crates/wre-env/src/capture.rs` | `cargo test -p wre-env` |
| Session | `src/aio_reverse/application/interactive_session.py` | `tests/test_interactive_session.py` |
| Use case | `src/aio_reverse/application/use_cases/run_web_scripts.py` | `tests/test_run_web_scripts.py` |
| Artifact | `src/aio_reverse/infrastructure/artifacts/run_store.py` | E2E artifact inspection |
| Toolkit | `src/aio_reverse/adapters/toolkit/wre_cli.py` | `tests/test_wre_cli.py` |
| CLI | `src/aio_reverse/main.py` + `cli/*.py` | `uv run aio-reverse web targets` |
| MCP | `src/aio_reverse/adapters/mcp/web_tools.py` | `tests/test_mcp_tools.py` + smoke |
| Config | `src/aio_reverse/infrastructure/config.py` | unit test/loader |
| Target data | `targets/chatgpt/*` | `web scripts chatgpt` |
| Skill catalog | `docs/skills/SKILL.md` + `references/*` | link checker + `SKILL.md` line count |
| Skill templates | `docs/skills/templates/*` | `python -m json.tool` cho JSON |
| ChatGPT behavior report | `docs/skills/examples/chatgpt/behavior-report.md` | đối chiếu run `20261025T115909Z-chatgpt` |
| Skill catalog report | `docs/report_skills_catalog_20261025.md` | đọc lại + `git status --short` |
| Artifact safety | `adapters/web/cdp/{turn_collector,cdp_values,response_bodies}.py` | `tests/test_cdp_routing.py` + replay fakechat |
| Script deadline | `application/action_engine.py` | `tests/test_action_engine.py` |
| Template CLI JSON | `libs/web-re-toolkit/crates/wre-cli/src/template_cmd.rs` | `cargo test -p wre-cli` + `wre --json template diff` |
| Template integration | `adapters/toolkit/wre_cli.py` + `application/use_cases/analyze_template.py` | `tests/test_template_analysis.py` |
| Page snapshot | `infrastructure/artifacts/html_snapshot_store.py` + `application/use_cases/capture_page_snapshot.py` | `tests/test_template_analysis.py` |
| Surface CLI/MCP | `cli/web_surface.py` + `adapters/mcp/web_tools.py` | `tests/test_mcp_tools.py` + replay |
| Replay matrix | `docs/report_replay_matrix_20261025.md` | fakechat + MCP smoke + ChatGPT thật |

## 6. Quy ước cập nhật tiến độ

- Tick checkbox ngay sau khi lệnh verify tương ứng pass; không tick trước.
- Mỗi phase ghi một dòng nhật ký, kèm số test hoặc output chính.
- Trạng thái mục 3 phải khớp checkbox của mục 4 trước khi kết thúc phase.
- Sai lệch thiết kế ghi thành dòng riêng, kèm lý do và ảnh hưởng.
- Không commit thay đổi thay người dùng; chỉ commit khi được yêu cầu.

## 7. Rủi ro & trade-off

| Rủi ro | Xử lý |
|---|---|
| ChatGPT đổi DOM | Fail loud với selector cụ thể; dùng `web state`/`web evaluate` để dò lại; ghi chú trong `targets/chatgpt/README.md` |
| `wre capture --profile` xung đột Chrome đang mở | Static capture là tùy chọn, không nằm trên đường chạy chính; dùng profile/port riêng |
| SSE/WS chỉ ghi metadata | Tránh phình artifact và rò payload; payload đã có qua CDP Network events |
| MCP `evaluate`/`navigate` nguy hiểm | Chỉ local stdio, validate scheme http/https, không expose ra mạng |
| Refactor xóa nhiều file | Làm theo phase, chạy test từng phase, commit theo yêu cầu |
| Profile chứa cookie | `data/profiles/` gitignored; không log nội dung profile |
| Artifact CDP chứa payload/cookie | Phase 10: redact header nhạy cảm, SSE/WS chỉ metadata trừ khi `stream_payloads=true`; body chỉ khi URL khớp `body_capture_patterns` |
| Snapshot HTML chứa nội dung thật | Chỉ ghi dưới `data/output/` (gitignored); MCP chỉ trả path/bytes/sha256; không dán vào docs |
| `wre --json template diff` đổi shape | `--slots` giữ mảng cũ; ghi "Sai lệch" khi hoàn tất Phase 11 |
| Hai snapshot giống nhau cho skeleton vô dụng | Tài liệu yêu cầu chụp 2 trạng thái khác nhau trước khi diff |

## 8. Nhật ký tiến độ

| Ngày | Phase | Kết quả | Lệnh verify | Ghi chú |
|---|---|---|---|---|
| 2026-10-25 | 0 | xong | — | Tạo file theo dõi, checklist Phase 1–8 |
| 2026-10-25 | 1 | xong | `cargo test -p wre-probe` | 15 test pass; `drain()` giữ stream còn mở với counter reset, bỏ stream đã đóng sau lượt kế tiếp |
| 2026-10-25 | 2 | xong | `cargo test -p wre-target -p wre-cli`; `wre probe emit`; `node --check` | 9 test pass; release build; emit 16.7 KB (flag) và 19.6 KB (target manifest); 3 case lỗi exit 1 đúng thông điệp |
| 2026-10-25 | 3 | xong | `uv run python -m unittest tests.test_web_target tests.test_action_script -v` | 40 test pass (11 target/registry + 29 action script); thêm `targets/chatgpt/` và config `profiles_dir`; module cũ giữ tạm tới Phase 7 |
| 2026-10-25 | 4 | xong | `uv run python -m unittest tests.test_cdp_routing -v`; `uv run python -m unittest discover -s tests` | 28 test CDP pass; full suite 108 pass; adapter 1066 dòng tách thành `adapters/web/cdp/` (7 module), xóa file cũ; `drain_probe` fail loud khi thiếu `__WRE`; `press` hỗ trợ 4 phím whitelist |
| 2026-10-25 | 5 | xong | `uv run python -m unittest discover -s tests` (129 pass); `uv run aio-reverse web targets`; `web scripts chatgpt`; `web probe chatgpt > /tmp/aio-probe-chatgpt.js && node --check` | 129 test pass (21 test mới: engine 5, session 8, use case 5, toolkit 3); artifact `turn-NN/*.json` đầy đủ; probe thật 19,494 bytes qua `node --check`. `web run` với Chrome/ChatGPT thật hoãn sang Phase 8. |
| 2026-10-25 | 6 | xong | `uv run python -m unittest discover -s tests` (140 pass); MCP client stdio `initialize` + `tools/list` + `web_targets` | 140 test pass (11 test MCP/registry); server trả đúng 11 tool; `web_targets` đọc `targets/chatgpt/target.json`; `SessionRegistry` giữ 1 session/target và `close_all` luôn thử đóng hết rồi báo lỗi đầu tiên. |
| 2026-10-25 | 7 | xong | `rg` legacy symbols (không khớp); `uv run python -m unittest discover -s tests` (112 pass); `cargo test -p wre-probe -p wre-target -p wre-cli` (24 pass) | Xóa 8 module/dir cũ + 3 test cũ; `targets/__init__.py` chỉ còn docstring; README và `docs/capture_analystic.md` mô tả kiến trúc mới; 112 test Python pass trong 0.303s; Rust 15 + 9 pass. Báo cáo: `docs/report_legacy_cleanup_20261025.md`. |
| 2026-10-25 | 8 | một phần | `web probe chatgpt` (19,494 bytes) + `node --check`; `web login fakechat`; `web run fakechat` 2 lượt; MCP stdio 4 tool; full suite 112 pass | Fakechat: turn 1 chỉ có `turn=1`, turn 2 chỉ có `turn=2` ở cả probe và CDP; mỗi lượt `network=1`, `sse=1` (3 message), `websocket=1` (2 frame), `reads=2`, `calls=2` → `drain()` đúng. MCP smoke trả 11 tool và chạy thành công `web_open → web_run_script → web_state → web_close`. ChatGPT thật chưa chạy vì cần đăng nhập thủ công. Báo cáo: `docs/report_e2e_phase8_20261025.md`. |
| 2026-10-25 | 8 | xong | `web login chatgpt`; `web run chatgpt` ×2; `cargo test -p wre-env`; `cargo build --release -p wre-cli`; full suite 116 pass; `web state` sau khi dừng Chrome | ChatGPT thật: setup 3 step + turn 6/6 step, 26 request/17 matched, probe reads 18/calls 11/events 82/network 17/websocket 1, CDP WebSocket 7 frame. Run cuối `20261025T115909Z-chatgpt` có 0 console error/0 exception; run đầu có 13 unhandled rejection từ env capture (đã sửa). Dừng Chrome rồi `web state` pass, không cần login lại. Selector mới: ProseMirror composer, `aria-label=Send/Stop/New chat`, `h4[data-conversation-role=assistant]`. Báo cáo: `docs/report_chatgpt_e2e_20261025.md`. |
| 2026-10-25 | 9 | xong | link checker + JSON parse + `SKILL.md` line count; `uv run python -m unittest discover -s tests` (116 pass) | Tạo `docs/skills/` gồm 1 master skill, 9 reference playbook, 3 template, 5 tài liệu ca ChatGPT. Báo cáo hành vi dựa trên run thật, tách Observed/Inferred/Unknown; không có body/token/ID. Phát hiện 3 gap: (1) `network_patterns` vừa lọc summary vừa bật response-body capture; (2) `ActionScript.timeout_s` chưa enforce; (3) CDP `sse.json`/`websocket.json` có payload trong khi probe chỉ ghi metadata. Báo cáo: `docs/report_skills_catalog_20261025.md`. |
| 2026-10-25 | wre-template | xong | `cargo test -p wre-template`; `cargo clippy -p wre-template`; `wre template diff` | 10 test pass (8 unit + 2 integration); clippy clean; dual-hash `hash_raw` vs `hash_norm` khử fake dynamic (timestamp, counter); bảo tồn label-sibling context và semantic whitelist; CLI `wre template diff` bóc tách skeleton giảm 70-90% token cho LLM. Báo cáo: `docs/report_wre_template_crate_20261025.md`. |
| 2026-10-25 | 10 | xong | `uv run python -m unittest discover -s tests` (134 pass); `web run chatgpt` ×2 (trước/sau sửa probe); `web run fakechat` 2 lượt; target tạm strict | Tách `body_capture_patterns` khỏi `network_patterns`; header nhạy cảm → `[redacted]`; SSE/WS mặc định chỉ metadata; request body chỉ metadata; enforce deadline script. Replay ChatGPT `20261025T133736Z-chatgpt`: 18 request, 0 raw body/stream, 43 header redacted, probe 12 entry (7 body_redacted), 6/6 step, 0 exception. Phát hiện và vá gap probe body sample. Báo cáo: `docs/report_artifact_safety_20261025.md`, `docs/report_chatgpt_chat_flow_20261025.md`. |
| 2026-10-25 | 11 | xong | `cargo test -p wre-template -p wre-cli` (15 pass); full suite `unittest discover` (159 pass); `node --check` probe; `web snapshot` home/thread + `web skeleton --xpath` trên ChatGPT thật; `rg` leak scan rỗng; `git status data/output` rỗng | `wre --json template diff` trả object 5 key; `WreToolkit.template_diff` fail loud; `outer_html()` cap 8 MiB; `HtmlSnapshotStore` chống ghi đè; `CapturePageSnapshotUseCase` + `AnalyzeTemplateUseCase`; CLI `web snapshot`/`web skeleton`; MCP 13 tool. Replay ChatGPT: `20261025T142753Z-home.html` (768.519 B) + `20261025T150041Z-thread.html` (816.802 B) → reduction 0.9631, 6 slot, vùng động đúng ở scroll container hội thoại + portal. `send_prompt` fail "Failed to fetch" 4 lần (lỗi client-side phía ChatGPT), Retry 1 lần → thread hoàn tất server-side. Báo cáo: `docs/report_template_integration_20261025.md`. |
| 2026-10-25 | 12 | xong | Policy scan `20261025T133736Z-chatgpt/turn-01` (0 body, 0 header lộ, WS metadata-only); MCP stdio smoke 13 tool: `web_targets` → `web_state` → `web_snapshot` (816.802 B) → `web_skeleton` → `web_close` giữ Chrome; link checker `docs/skills` rỗng; `SKILL.md` 314 dòng | Matrix replay chuyển sang ChatGPT thật theo chỉ đạo người dùng (fakechat nằm ở unit test). Không gọi `web_run_script` qua MCP để tránh thêm lượt gửi thật. Docs: gate 2 skeleton-first (SKILL.md + refs 03), 2 CLI + 2 MCP tool (ref 09), JSON shape + đường Python (ref 10). Báo cáo: `docs/report_replay_matrix_20261025.md`. |

### Sai lệch so với kế hoạch

| Ngày | Phase | Sai lệch | Lý do |
|---|---|---|---|
| 2026-10-25 | 3 | Template được render tại runtime (`resolve_action`) thay vì render toàn bộ lúc load; loader chỉ validate cấu trúc và expose `required_variables()` | `save` của action trước cấp biến cho action sau (`send_prompt`: `count` save `replies_before` rồi `wait_count` dùng lại), nên không thể render đủ ở load-time. Lỗi thiếu biến vẫn fail loud kèm tên biến. |
| 2026-10-25 | 4 | Thêm module `cdp_values.py` ngoài 6 module đã liệt kê; `drain_probe()` raise `ProbeUnavailableError` thay vì trả `None` | `turn_collector` và `chrome_cdp_session` cùng cần bộ đọc giá trị CDP; tách riêng tránh lặp logic. `drain_probe` là đường dữ liệu probe duy nhất mỗi lượt nên thiếu `__WRE` phải fail loud, không trả rỗng âm thầm. |
| 2026-10-25 | 5 | Tách CLI thành `cli/composition.py`, `cli/web_probe.py`; thêm `application/turn_summary.py`; giữ tạm `legacy_run_store.py` cho test cũ | Không dùng file tên chung `common.py` theo quy ước repo; `web probe` cần module riêng. Summary dùng chung cho use case và artifact. Test `test_run_web_flow.py` cũ cần store cũ tới khi Phase 7 xóa. |
| 2026-10-25 | 6 | Dùng `MCPServer` thay `FastMCP`; chuyển composition root sang `src/aio_reverse/composition.py` dùng chung CLI + MCP | MCP 2.x đã đổi tên `FastMCP` thành `MCPServer` (`mcp.server.mcpserver`). Composition root đặt ngoài `cli/` để adapter MCP không phụ thuộc ngược vào CLI, tránh lặp logic dựng session/store. |
| 2026-10-25 | 7 | Xóa thêm `infrastructure/artifacts/legacy_run_store.py`, `tests/test_targets.py`, `tests/test_flow_runner.py`, `tests/test_run_web_flow.py` và cả thư mục `experiments/` | Các file chỉ phục vụ kiến trúc cũ; giữ lại sẽ tham chiếu symbol đã xóa và làm sai lệch số test. `experiments/chatgpt.py` là entrypoint duy nhất còn lại của thư mục nên xóa cả thư mục. |
| 2026-10-25 | 8 | Server fake chat đặt trong `tests/fixtures/fake_chat_server.py`, nhưng target `fakechat` phải nằm trong `targets/fakechat/` thay vì hoàn toàn trong `tests/fixtures/` | `TargetRegistry` quét cố định `PROJECT_ROOT/targets/*/target.json`; không có cơ chế trỏ registry sang thư mục fixture và không thêm cấu hình mới chỉ cho test. Target fakechat được ghi chú rõ là fixture cục bộ, không gọi dịch vụ ngoài. |
| 2026-10-25 | 8 | Chưa chạy `web login chatgpt` / `web run chatgpt` | Môi trường tự động không có phiên đăng nhập ChatGPT và không được tự động hóa credential; cần người dùng đăng nhập tay trong Chrome profile `data/profiles/chatgpt`. |
| 2026-10-25 | 8 | `click`/`count`/`wait_visible`/`wait_hidden`/`wait_count` chỉ xét phần tử đang render (kích thước > 0, không `visibility:hidden`) thay vì mọi node khớp selector | ChatGPT giữ DOM của route cũ trong workspace `display:none`. Nếu không lọc, `count`/`wait_count` đếm tin nhắn ẩn và `click` bấm phần tử 0×0. Logic tập trung tại `application/page_element_expressions.py`. |
| 2026-10-25 | 8 | `CAPTURE` của `wre-env` gắn rejection handler cho getter trả thenable | Getter `ReadableStreamDefaultReader.closed` trả promise; không quan sát thì khi stream đóng promise reject thành unhandled rejection trong trang (13 lần ở run ChatGPT đầu). Test: `promise_getters_get_a_rejection_handler`. |
| 2026-10-25 | 8 | Ghi nhận cold start SPA có thể kẹt `readyState=interactive`; xử lý bằng reload trang rồi chạy lại | Trang ChatGPT khôi phục phiên có thể chưa hydrate sau khi Chrome restart; profile vẫn giữ đăng nhập. Không thêm auto-reload để tránh che lỗi auth/UI thật. |
| 2026-10-25 | 9 | Bổ sung Phase 9 ngoài roadmap gốc: skill catalog + báo cáo hành vi | Yêu cầu người dùng ngày 2026-10-25; phạm vi chỉ tài liệu, không sửa code. |
| 2026-10-25 | 9 | Gap: `network_patterns` đồng thời là bộ lọc summary và danh sách bật `Network.getResponseBody` | `collect_bodies()` dùng chính `target.network_patterns`; thêm pattern rộng vô tình lưu response body (tối đa 4 MB/response). Đề xuất tách `body_capture_patterns` (mặc định rỗng) hoặc cờ opt-in; chưa sửa vì task chỉ tài liệu. |
| 2026-10-25 | 9 | Gap: `ActionScript.timeout_s` được parse/validate nhưng `ActionEngine` không enforce | Chỉ `action.timeout_s` được dùng; script-level timeout không chặn tổng thời gian. Đề xuất deadline tổng trong engine hoặc bỏ trường để tránh hiểu nhầm; chưa sửa vì task chỉ tài liệu. |
| 2026-10-25 | 10 | Mặc định artifact đổi: request/SSE/WS raw payload biến mất; header nhạy cảm thành `[redacted]`; `network_patterns` không còn bật response body | Đóng 3 gap Phase 9. Fakechat bật `body_capture_patterns: ["/backend-api/"]` + `stream_payloads: true` để giữ fixture raw; ChatGPT để rỗng/false. Ai đọc artifact cũ cần biết `data`/`payload`/`request_body` có thể vắng mặt và dùng `*_bytes`/`*_sha256` thay thế. |
| 2026-10-25 | 10 | Bổ sung redaction cho `probe.json`: `network[].body` là sample ~200 ký tự do Rust probe ghi, vẫn chứa prompt; Python thay bằng `null` + `body_redacted: true` nếu URL không khớp `body_capture_patterns` | Phát hiện khi replay ChatGPT: CDP đã sạch nhưng probe vẫn lộ body sample. Không sửa Rust `wre-probe` (giữ nguyên crate); policy áp tại `application/probe_network_redaction.py` trước khi ghi artifact. |
| 2026-10-25 | 9 | Gap tài liệu: mục 9 ghi "không ghi payload SSE/WebSocket vào artifact", nhưng CDP `sse.json`/`websocket.json` có `data`/`payload` | Probe Rust chỉ ghi metadata; collector CDP ghi payload. Cần chính sách riêng cho artifact CDP (redaction/opt-in) và sửa lại câu chữ tài liệu. |
| 2026-10-25 | 11 | `wre --json template diff` đổi từ mảng slot sang object `{pages, first_page, reduction_ratio, skeleton, slots}` | Wrapper Python cần skeleton + slots + reduction trong một lần gọi, không parse text có phân cách. `--slots` giữ mảng cũ cho người dùng CLI hiện có. |
| 2026-10-25 | 11 | `text_metadata` dời từ `adapters/web/cdp/cdp_values.py` sang `domain/content_fingerprint.py` | CDP adapter và `HtmlSnapshotStore` (infrastructure) cần chung helper hash; đặt ở domain để application không import infrastructure (vi phạm layering nếu để trong adapters). |
| 2026-10-25 | 11–12 | Replay nghiệm thu chuyển từ fakechat sang ChatGPT thật | Chỉ đạo người dùng ngày 2026-10-25 ("không cần fakechat"); fakechat vẫn được coverage bởi 159 unit/integration test. |
| 2026-10-25 | 12 | MCP smoke không gọi `web_run_script`; dùng thread đã hoàn tất server-side để chụp snapshot thread | Chuỗi `send_prompt` fail "Failed to fetch" 4 lần (lỗi client phía ChatGPT, không phải pipeline); nguyên tắc giảm lượt, không spam — chỉ bấm Retry 1 lần trên nút sẵn có của trang. |

## 9. Việc chưa làm / ngoài phạm vi

- Phase B marker sweep của kế hoạch trước.
- Tự động đăng nhập / lấy credential.
- Ghi payload SSE/WebSocket **từ probe Rust** vào artifact. Lưu ý: collector CDP hiện vẫn
  ghi `data`/`payload` trong `turn-NN/sse.json` và `turn-NN/websocket.json`; cần chính
  sách redaction/opt-in riêng (xem Phase 9).
- Triển khai probe crate qua PyO3 hoặc nhúng V8 vào Python.
