# Báo cáo Phase 12 — Replay matrix + tài liệu — 2026-10-25

## 1. Đã làm gì

Chạy ma trận replay nghiệm thu cuối của kế hoạch Phase 10–12 và cập nhật toàn bộ
tài liệu skill. Theo chỉ đạo của người dùng ("không cần fakechat"), matrix chuyển
sang **ChatGPT thật**; fakechat vẫn được coverage ở tầng unit/integration test.

### 1.1 Policy audit trên run ChatGPT mới nhất (`20261025T133736Z-chatgpt/turn-01`)

Bằng script đọc JSON (không in giá trị):

| Kiểm tra | Kết quả |
|---|---|
| `network.json` | 18 entry — **0 raw body**, **0 sensitive header chưa redact** |
| `websocket.json` | 2 event — chỉ `payload_bytes`/`payload_sha256`, không `payload` (target `stream_payloads: false`) |
| `sse.json` | 0 event (lượt này trang không mở EventSource mới) |
| `probe.json` | 12 network sample — **0 body** (redaction Phase 10 hoạt động trên cả đường probe) |

### 1.2 MCP stdio smoke — 13 tool

Khởi `uv run aio-reverse mcp` qua JSON-RPC stdio:

- `tools/list` → **đúng 13 tool** (thêm `web_snapshot`, `web_skeleton`).
- `web_targets` → `['chatgpt', 'fakechat']`, info có `body_capture_patterns`, `stream_payloads`.
- `web_state` → attach phiên session registry vào thread đang mở (`https://chatgpt.com/c/{thread}`).
- `web_snapshot {label: "mcp-smoke"}` → 816.802 B (khớp kích thước snapshot thread CLI —
  cùng trạng thái page, proof path dùng chung `CapturePageSnapshotUseCase`).
- `web_skeleton {pages: [home, thread], xpath: true}` → `pages: 2`, `reduction_ratio: 0.9631`,
  6 slot, trả qua stdio chỉ skeleton + metadata.
- `web_close` → `closed: true`, `browser: "kept running"`; server exit 0.
- **Không gọi `web_run_script`** qua MCP: chuỗi `send_prompt` đã fail "Failed to fetch"
  4 lượt sáng nay (lỗi client phía ChatGPT) — tôn trọng nguyên tắc giảm lượt, không spam.

### 1.3 Replay ChatGPT (tóm tắt; chi tiết trong báo cáo Phase 11)

home snapshot `20261025T142753Z-home.html` (768.519 B) → thread snapshot
`20261025T150041Z-thread.html` (816.802 B) → skeleton `--xpath`: reduction **96.3%**,
122 dòng, 6 slot. Vùng động đúng như kỳ vọng: scroll container hội thoại (`← [dynamic]`),
greeting xoay vòng trên home, portal root `body > div[5]`; nav/sidebar/header/composer
prune. `git status --short data/output` rỗng — snapshot nằm ngoài git.

### 1.4 Tài liệu cập nhật

| File | Thay đổi |
|---|---|
| `docs/skills/SKILL.md` | Gate 2 thêm khối **skeleton-first** (chụp 2 trạng thái → diff → inventory trong vùng dynamic); command map thêm `web snapshot`, `web skeleton` (314 dòng, < 500) |
| `docs/skills/references/03-surface-mapping.md` | Thêm **Bước 1b — Skeleton-first** kèm lệnh + điều kiện "hai trạng thái thực sự khác" + số liệu ChatGPT (96.3%, 6 slot) |
| `docs/skills/references/09-toolkit-command-map.md` | CLI block + bảng ngữ nghĩa phiên (`snapshot`: mở session/ghi snapshots/giữ Chrome; `skeleton`: không session) + 2 hàng MCP tool + chú thích cap 8 MiB/chống ghi đè/không trả HTML + "tổng cộng 13 tool" |
| `docs/skills/references/10-html-processing-and-autocrawl.md` | Mục 2.1 thêm `wre --json template diff` (object 5 key) + "Đường Python" (snapshot/skeleton + MCP) |
| `docs/plans.md` | Tick toàn bộ Phase 11–12, 2 dòng nhật ký, 4 dòng Sai lệch (JSON shape, dời `text_metadata` sang domain, đổi fakechat → ChatGPT, bỏ `web_run_script` trong smoke), 2 dòng bảng trạng thái |
| `docs/report_template_integration_20261025.md` | Báo cáo Phase 11 (đã viết trước báo cáo này) |

## 2. Lệnh verify + kết quả thực tế

```bash
uv run python -m unittest discover -s tests        # Ran 159 tests — OK
cargo test -p wre-template -p wre-cli              # 13 + 2 passed, 0 failed
uv run aio-reverse web probe chatgpt | node --check # PROBE_OK
rg 'Cookie: |Authorization: |payloadData|sk-…' docs/skills data/output/web/fakechat  # rỗng
git status --short data/output                     # rỗng
```

- Link checker nội bộ `docs/skills`: **0 link gãy**; `grep TODO:` rỗng.
- MCP smoke in `SMOKE_OK exit 0` và `SNAPSHOT_SMOKE_OK` (mục 1.2).
- Warning cargo `unused import: json` tại `crates/wre-sandbox/src/profile.rs:4` —
  **có sẵn từ trước, ngoài phạm vi Phase 10–12**, không sửa; đề xuất dọn khi chạm crate đó.

## 3. Trạng thái cuối

- Kế hoạch Phase 10–12: **hoàn tất cả 3 phase** (13/13 + 11/11 + 8/8 dòng tick,
  Sai lệch ghi đủ 4 dòng mới).
- Pipeline đầy đủ trên target thật:
  `login (tay) → snapshot home → run (measured turn) → snapshot thread → skeleton → MCP handover`.
- Chưa commit (theo yêu cầu); mọi thay đổi nằm trong working tree.
- Ràng buộc an toàn giữ nguyên: không bypass, Retry đúng 1 lần trên nút của trang,
  ID hội thoại không vào docs, HTML snapshot chỉ nằm trong `data/output` (gitignored).
