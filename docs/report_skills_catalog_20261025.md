# Báo cáo — Skill catalog phân tích web + ca thực nghiệm ChatGPT

> Ngày: 2026-10-25
> Phạm vi: tạo `docs/skills/` và báo cáo hành vi dựa trên run thật
> `20261025T115909Z-chatgpt`.
> Không sửa source code. Không commit. Không có cookie/token/body/prompt thật/ID hội thoại
> trong tài liệu.

## 1. Mục tiêu

1. Tạo một **skill catalog** trong repo để hướng dẫn phân tích một trang web và thiết kế
   chuỗi hành động đạt mục tiêu, dùng đúng các crate Rust qua sidecar `wre`.
2. Lấy ChatGPT làm **ca thực nghiệm**, viết báo cáo chi tiết "web hoạt động thế nào"
   **trước khi** viết bất kỳ code tích hợp nào.
3. Đảm bảo skill chỉ dùng primitive hiện có; nếu phát hiện gap thì ghi nhận + đề xuất,
   không tự mở rộng engine.

## 2. Đã tạo gì, ở đâu

Tổng cộng **18 file** dưới `docs/skills/`:

| Nhóm | File | Nội dung |
|---|---|---|
| Master | `docs/skills/SKILL.md` | Quy trình 7 cổng, non-negotiables, danh mục module, lệnh tối thiểu, code gate |
| Reference | `references/01-authorization-and-scope.md` | Mission contract, quyền, dữ liệu, điều kiện dừng |
| Reference | `references/02-session-and-target-config.md` | Profile, `target.json`, probe, CLI/MCP |
| Reference | `references/03-surface-mapping.md` | DOM map, visibility, selector ranking, snippet read-only |
| Reference | `references/04-action-chain-design.md` | 11 action type, template/save, timeout, anti-pattern |
| Reference | `references/05-network-and-stream-analysis.md` | CDP/probe, SSE/WS/fetch-stream, telemetry, integrity |
| Reference | `references/06-artifact-forensics.md` | Layout artifact, thứ tự đọc, kiểm tra drain/nhất quán |
| Reference | `references/07-behavior-report.md` | 11 mục bắt buộc, độ tin cậy, code gate |
| Reference | `references/08-failure-playbook.md` | Bảng triệu chứng → nguyên nhân → xử lý |
| Reference | `references/09-toolkit-command-map.md` | Lệnh `aio-reverse`, `wre`, 11 MCP tool, đường dẫn dữ liệu |
| Template | `templates/behavior-report.md` | Khung báo cáo hành vi |
| Template | `templates/target.json` | Khung target hợp lệ |
| Template | `templates/action-script.json` | Khung action chain có count delta + wait |
| Example | `examples/chatgpt/behavior-report.md` | Báo cáo hành vi đầy đủ 14 mục |
| Example | `examples/chatgpt/dom-map.md` | Selector, state matrix, snippet kiểm tra |
| Example | `examples/chatgpt/network-map.md` | Bảng endpoint path-only, transport, nhiễu |
| Example | `examples/chatgpt/action-chain.md` | Chain setup/turn, số đo, tín hiệu lỗi |
| Example | `examples/chatgpt/lessons.md` | 12 bài học chuyển giao |

## 3. Nội dung cốt lõi

### 3.1 Quy trình bảy cổng

```text
Mission → Session → Surface map → Behaviour map → Action chain design
        → Dry run → Measured run → Artifact forensics → Report → Code gate
```

Master skill quy định: không viết code tích hợp trước khi báo cáo hành vi trả lời đủ
state machine, selector raw/rendered, request ↔ action, transport stream, tín hiệu hoàn
tất, artifact chứng minh và rủi ro.

### 3.2 Phối hợp crate

Skill mô tả đúng ranh giới hiện có:

- Rust `wre` sở hữu browser, probe, env script, capture.
- Python là wrapper mỏng: target config, action script, artifact, CLI/MCP.
- `wre probe emit` → inject một lần/navigation; `drain()` mỗi turn.
- `wre env script` + evaluate trong phiên sống; **không** dùng `wre env snapshot` giữa
  chain vì nó navigate.
- `wre capture` là static capture, profile/port riêng, không nằm trên đường `web run`.

### 3.3 Ca ChatGPT

Báo cáo dựa trên run thật `20261025T115909Z-chatgpt`:

| Chỉ số | Giá trị |
|---|---|
| Steps | 6/6 |
| Requests | 26 (17 khớp pattern) |
| Probe | reads 18, calls 11, events 82, network 17, sse 0, websocket 1 |
| CDP WebSocket | 7 frame |
| Console errors | 0 |
| Exceptions | 0 |
| Thời lượng turn | ~49.23 s |

Nội dung chính:

- SPA giữ DOM route cũ với `display:none` → mọi count/wait/click phải render-aware.
- Composer ProseMirror trong `form[data-chatgpt-composer]`; home/thread placement.
- Tín hiệu xong: `button[aria-label="Stop"]` biến mất + network quiet.
- `probe.sse=0` nhưng trang stream bằng `fetch` + WebSocket; không kết luận sai.
- Chuỗi đã kiểm chứng: count delta → type → click Send → wait_count → wait Stop hidden →
  wait network quiet.

Báo cáo tách rõ **Observed / Inferred / Unknown**, không có body/token/ID.

## 4. Gap phát hiện khi đối chiếu code (đề xuất, chưa sửa)

| # | Gap | Bằng chứng | Đề xuất |
|---|---|---|---|
| 1 | `network_patterns` vừa lọc summary vừa bật response-body capture | `ChromeCdpSession.end_turn` → `collect_bodies(..., self._network_patterns)`; body lưu vào `network.json` (tối đa 4 MB/response) | Tách `body_capture_patterns` (mặc định rỗng) hoặc cờ opt-in; giữ `network_patterns` chỉ để lọc báo cáo |
| 2 | `ActionScript.timeout_s` không được enforce | `ActionEngine.run` chỉ dùng `action.timeout_s`; script-level chỉ validate | Thêm deadline tổng hoặc bỏ trường để tránh hiểu nhầm |
| 3 | Tài liệu nói không ghi payload SSE/WS, nhưng CDP vẫn ghi | `turn_collector._sse_event` ghi `data`; `_ws_frame` ghi `payload` | Chính sách redaction/opt-in cho artifact CDP; sửa câu chữ tài liệu (đã ghi nhận trong `docs/plans.md`) |

Ngoài ra, mục 9 của `docs/plans.md` đã được sửa để phân biệt "probe chỉ ghi metadata" và
"CDP có payload".

## 5. Không vi phạm quy ước

- **Fail loud:** tài liệu yêu cầu dừng và báo lỗi đúng bước/selector; không fallback.
- **DRY:** logic expression/visibility được trỏ về một nguồn
  `application/page_element_expressions.py`, không lặp snippet trong code.
- **Một file một trách nhiệm:** mỗi reference/template/example có một chủ đề.
- **Không speculation:** các mục chưa kiểm chứng được đánh dấu Unknown; không thêm code.
- **Báo cáo:** file này + cập nhật `docs/plans.md`.
- **Không secret:** đã quét pattern token/UUID/token dài; không khớp.

## 6. Lệnh verify và kết quả thực tế

### 6.1 Cấu trúc và nội dung

```bash
find docs/skills -type f | sort
wc -l docs/skills/SKILL.md
```

Kết quả:

```text
18 file (5 master+reference, ... xem mục 2)
301 docs/skills/SKILL.md
```

`SKILL.md` < 500 dòng theo khuyến nghị skill-creator.

### 6.2 Frontmatter, JSON, link nội bộ

```bash
python3 - <<'PY'
# kiểm tra frontmatter name/description, parse template JSON,
# resolve 19 link nội bộ
PY
```

Kết quả:

```text
JSON OK   docs/skills/templates/action-script.json
JSON OK   docs/skills/templates/target.json
FRONTMATTER OK
LINKS OK (19 internal links)
DOC CHECKS OK
```

### 6.3 Quét dữ liệu nhạy cảm

```bash
grep -rEn 'Bearer [A-Za-z0-9]|sk-[A-Za-z0-9]{10,}|session_token|access_token|Set-Cookie|6addef3a|user-bvrf|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' docs/skills
```

Kết quả:

```text
none
```

### 6.4 Test suite

```bash
uv run python -m unittest discover -s tests
```

Kết quả:

```text
Ran 116 tests in 0.298s

OK
```

Không có source code thay đổi; test suite xác nhận tài liệu không ảnh hưởng code.

### 6.5 Trạng thái git

```bash
git status --short docs/skills docs/plans.md
```

Kết quả:

```text
?? docs/plans.md
?? docs/skills/
```

Toàn bộ `docs/` đang untracked trong working tree; không commit.

## 7. Cách dùng

1. Đọc `docs/skills/SKILL.md` trước.
2. Chọn module theo bảng "Danh mục module".
3. Dùng `templates/behavior-report.md` cho target mới.
4. Đối chiếu ca ChatGPT khi cần ví dụ đầy đủ.
5. Nếu muốn Qoder tự nạp skill:

```bash
mkdir -p .qoder/skills
ln -s ../../docs/skills .qoder/skills/web-surface-recon
```

## 8. Chưa làm / giới hạn

- Không cài symlink vào `.qoder/skills` (chỉ ghi lệnh tùy chọn).
- Không chạy thêm prompt/probe mới trên ChatGPT; báo cáo dùng artifact run đã có.
- Không sửa 3 gap ở mục 4; cần task code riêng.
- Không commit.
