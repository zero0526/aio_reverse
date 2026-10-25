# Báo cáo Phase 11 — Tích hợp `wre-template` (snapshot + skeleton) — 2026-10-25

## 1. Đã làm gì

Toàn bộ checklist Phase 11 trong `docs/plans.md` đã hoàn tất và verify.
Replay nghiệm thu chạy trên **ChatGPT thật** (theo chỉ đạo của người dùng: bỏ qua fakechat).

### 11.1 Rust CLI (`wre template diff`)
- `--json` trả object có cấu trúc `{pages, first_page, reduction_ratio, skeleton, slots}`;
  `--slots` giữ mảng tương thích cũ; plain mode không đổi.
- File: `libs/web-re-toolkit/crates/wre-cli/src/template_cmd.rs`, `src/args.rs`.

### 11.2–11.6 Python core
- `IToolkitPort.template_diff(pages, *, xpath)` + `WreToolkit.template_diff`
  (argv `template diff [--xpath] <pages...>`, validate fail-loud: `skeleton` str khác rỗng,
  `slots` list, `pages` int ≥ 2, `reduction_ratio` 0..1 — lỗi kèm command/stdout).
- `IBrowserSessionPort.outer_html()` + `ChromeCdpSession.outer_html()`
  với `MAX_SNAPSHOT_BYTES = 8 MiB` (vượt → `BrowserSessionError` nêu kích thước, không cắt).
- `infrastructure/artifacts/artifact_naming.py`: `safe_name`/`utc_stamp` dùng chung
  (`run_store.py` đã bỏ bản private — DRY).
- `HtmlSnapshotStore` ghi `data/output/web/<target>/snapshots/<utc>-<label>.html`,
  từ chối ghi đè (FileExistsError), trả `SnapshotFile{label, path, bytes, sha256}`.
- `AppConfig.html_snapshots_dir(target)`.
- `PageSnapshot` + `IWebSession.capture_page(label)` + `CapturePageSnapshotUseCase`
  (caller sở hữu session; use case không open/close).
- `AnalyzeTemplateUseCase` validate ≥ 2 file `.html` tồn tại trước khi gọi toolkit.
- `text_metadata` dời sang `domain/content_fingerprint.py` để CDP adapter và
  snapshot store dùng chung mà application không import infrastructure.

### 11.7 CLI + MCP
- CLI mới `cli/web_surface.py`: `web snapshot <target> --label NAME [--json]`,
  `web skeleton --page P --page P [--xpath] [--json]`; đăng ký trong `main.py`.
- MCP thêm `web_snapshot`, `web_skeleton` → **13 tool**; `_target_info` thêm
  `body_capture_patterns`, `stream_payloads`.

## 2. Làm tại đâu (file chính)

| Nhóm | File |
|---|---|
| Rust | `crates/wre-cli/src/template_cmd.rs`, `crates/wre-cli/src/args.rs` |
| Toolkit | `src/aio_reverse/application/ports/toolkit_port.py`, `src/aio_reverse/adapters/toolkit/wre_cli.py`, `tests/fixtures/fake_wre.py` |
| CDP | `src/aio_reverse/application/ports/browser_session_port.py`, `src/aio_reverse/adapters/web/cdp/chrome_cdp_session.py` |
| Artifacts | `src/aio_reverse/infrastructure/artifacts/{artifact_naming,html_snapshot_store,run_store}.py`, `src/aio_reverse/infrastructure/config.py`, `src/aio_reverse/domain/content_fingerprint.py` |
| Use case | `src/aio_reverse/application/{page_snapshot,interactive_session}.py`, `src/aio_reverse/application/ports/web_session_port.py`, `src/aio_reverse/application/use_cases/{capture_page_snapshot,analyze_template}.py` |
| Surface | `src/aio_reverse/cli/web_surface.py`, `src/aio_reverse/main.py`, `src/aio_reverse/adapters/mcp/{web_tools,server}.py` |
| Test | `tests/{test_wre_cli,test_cdp_routing,test_html_snapshot_store,test_capture_page_snapshot,test_analyze_template,test_interactive_session,test_mcp_tools}.py`, `tests/fixtures/template_pages/{chat-home,chat-thread}.html` |
| Composition | `src/aio_reverse/composition.py` (`build_snapshot_store`) |

## 3. Lệnh verify + kết quả thực tế

| Lệnh | Kết quả |
|---|---|
| `cargo test -p wre-template -p wre-cli` | **ok** — 13 passed + 2 passed, 0 failed |
| `uv run python -m unittest discover -s tests` | **Ran 159 tests — OK** |
| `uv run aio-reverse web probe chatgpt \| node --check` | **PROBE_OK** |
| `rg 'Cookie: \|Authorization: \|payloadData\|sk-…' docs/skills data/output/web/fakechat` | **không khớp** (rỗng) |
| `git status --short data/output` | **rỗng** — snapshot nằm ngoài git |

## 4. Replay ChatGPT thật (nghiệm thu)

1. `web snapshot chatgpt --label home` (sau cold-start) →
   `data/output/web/chatgpt/snapshots/20261025T142753Z-home.html` (768.519 B,
   sha256 `29e1ad54…37e3`).
2. `web run chatgpt --script send_prompt --var prompt=ping` **thất bại 4 lần**
   (`wait_count 'h4[data-conversation-role="assistant"]'` vượt deadline; UI báo
   **"Failed to fetch"** + Retry — lỗi tầng mạng phía client, không phải rate-limit text;
   không có `turn-01/` vì run ghi artifact chỉ khi lượt hoàn tất).
3. Bấm **Retry đúng 1 lần** bằng trusted CDP mouse event trên nút của chính trang
   (không tự động hóa lại, không spam). Thread "Ping pong response" hoàn tất phía server
   (mục mới xuất hiện trong Recents).
4. Chrome kẹt "Loading profile" → `wre browser --port 9445 --stop` → cold-start lại
   (mẫu lỗi đã ghi nhận ở Phase 9: lệnh đầu sau restart fail readyState, retry sau ~40s pass).
5. `web navigate` vào thread đã hoàn tất → poll raw CDP: `assistant: 1, composer: 1,
   ready: complete, failed: false`.
6. `web snapshot chatgpt --label thread` →
   `20261025T150041Z-thread.html` (816.802 B, sha256 `1579b569…df73`).
7. `web skeleton --page <home> --page <thread> --xpath [--json]`:
   - `pages: 2`, `reduction_ratio: 0.9631`, **6 slot**, skeleton 122 dòng (plain 96.3%).
   - Slot động nằm đúng vùng hội thoại (scroll container `main > div… > div[2]`),
     greeting xoay vòng trên home ("What's on the agenda today?") và portal root `body > div[5]`.
   - Nav/sidebar/header/composer bị prune — giữ nguyên cấu trúc tĩnh.

Kết luận: skeleton từ hai trạng thái thật **thực sự khác nhau**; đường
snapshot → skeleton hoạt động end-to-end trên ChatGPT.

## 5. Ghi chú / sai lệch so với plan

- Plan ghi replay trên **fakechat**; người dùng chỉ đạo đổi sang ChatGPT thật —
  đã tick kèm chú thích trong `docs/plans.md`.
- `wre --json template diff` đổi mảng → object (quyết định #6); `--slots` giữ format cũ.
- 4 run `send_prompt` fail sáng nay để lại `run.json` fail trong `data/output/web/chatgpt/`
  (hành vi fail-loud đúng thiết kế, không có artifact lượt nào một phần).
- Warning cargo `unused import: json` ở `crates/wre-sandbox/src/profile.rs:4` là **có sẵn**,
  ngoài phạm vi Phase 11 (không sửa crate khác); đề xuất dọn ở lần chạm `wre-sandbox` tới.
- Constraint an toàn giữ nguyên: không bypass, chỉ bấm Retry 1 lần trên nút có sẵn của trang;
  ID hội thoại không xuất hiện trong báo cáo này (`{thread}`), HTML snapshot chỉ nằm
  trong `data/output` (gitignored), MCP/CLI chỉ trả path + hash.
