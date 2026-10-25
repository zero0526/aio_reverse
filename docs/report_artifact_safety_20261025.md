# Báo cáo Phase 10 — An toàn artifact + deadline action script

> Ngày: 2026-10-25
> Phạm vi: `src/aio_reverse/{application,targets,adapters/web/cdp,infrastructure}`,
> `targets/{chatgpt,fakechat}/target.json`, `tests/*`, `docs/skills/{references,templates}`.
> Trạng thái: xong phần code/test/replay; Phase 11 chưa bắt đầu.

## 1. Mục tiêu

Đóng 3 gap phát hiện ở Phase 9 trước khi sinh artifact HTML:

1. `network_patterns` vừa lọc summary vừa bật response-body capture.
2. `ActionScript.timeout_s` được parse nhưng không được enforce.
3. CDP `sse.json`/`websocket.json` lưu raw payload dù probe chỉ ghi metadata.

Thêm một gap phát hiện trong replay ChatGPT: probe `network[].body` vẫn lưu sample
request body (~200 ký tự), tức prompt vẫn rò vào `probe.json`.

## 2. Thay đổi và vị trí

| File | Thay đổi |
|---|---|
| `src/aio_reverse/application/action_engine.py` | Deadline tổng `script.timeout_s`; cap `timeout_s` từng action theo thời gian còn lại; lỗi `ActionScriptError` có chữ `timeout` và `step_index` |
| `src/aio_reverse/targets/web_target.py` | Thêm `body_capture_patterns: tuple[str, ...] = ()`, `stream_payloads: bool = False`; validate rỗng/không phải bool |
| `src/aio_reverse/targets/target_loader.py` | Parse 2 key mới; vẫn reject unknown keys |
| `src/aio_reverse/adapters/web/cdp/cdp_values.py` | Redact `cookie`, `set-cookie`, `authorization`, `proxy-authorization` → `[redacted]`; helper `text_metadata()` |
| `src/aio_reverse/adapters/web/cdp/turn_collector.py` | Request body chỉ raw khi URL khớp `body_capture_patterns`; luôn có `request_body_bytes`/`request_body_sha256`; SSE/WS chỉ metadata trừ khi `stream_payloads` |
| `src/aio_reverse/adapters/web/cdp/chrome_cdp_session.py` | Nhận `body_capture_patterns` + `stream_payloads`; `end_turn()` truyền pattern cho `collect_bodies` |
| `src/aio_reverse/composition.py` | Truyền policy từ target vào session |
| `src/aio_reverse/application/probe_network_redaction.py` | **Mới**: thay `probe.network[].body` bằng `null` + `body_redacted: true` nếu URL không khớp `body_capture_patterns` |
| `src/aio_reverse/application/interactive_session.py` | Áp `redact_probe_network()` sau `drain_probe()` trước khi tạo `SessionTurn` |
| `targets/chatgpt/target.json` | `body_capture_patterns: []`, `stream_payloads: false` |
| `targets/fakechat/target.json` | `body_capture_patterns: ["/backend-api/"]`, `stream_payloads: true` (fixture cần raw) |
| `tests/test_action_engine.py` | 2 test deadline |
| `tests/test_cdp_routing.py` | 3 test redaction; 2 test body capture; 2 test stream policy; 1 test wiring `end_turn` |
| `tests/test_web_target.py` | 4 test default/override/lỗi cho 2 key mới |
| `tests/test_probe_network_redaction.py` | **Mới**: 7 test policy probe |
| `tests/test_interactive_session.py` | 1 test tích hợp policy probe |
| `docs/skills/references/05-network-and-stream-analysis.md` | Bảng 3 lớp bằng chứng + policy mới + checklist |
| `docs/skills/references/06-artifact-forensics.md` | Field metadata mới, cảnh báo header redacted, policy probe |
| `docs/skills/templates/target.json` | Thêm 2 key mới |
| `docs/plans.md` | Tick Phase 10, thêm sai lệch policy |

## 3. Kết quả test

```text
uv run python -m unittest discover -s tests
Ran 134 tests in 0.311s
OK
```

Tăng từ 126 lên 134 test (8 test mới cho probe redaction + tích hợp; các test
deadline/redaction/body/stream đã thêm trước đó).

## 4. Replay

### 4.1 Fakechat — giữ raw để làm fixture

```bash
uv run python tests/fixtures/fake_chat_server.py --port 8765 &
uv run aio-reverse web login fakechat
uv run aio-reverse web run fakechat --script send_prompt --script send_prompt --var prompt=ping --json
```

Run `20261025T131853Z-fakechat`: `completed`, 2 turn, 6 step, 4 request, 6 SSE, 4 WS.
Vì fakechat bật `body_capture_patterns` + `stream_payloads`, raw `request_body`, `body`,
`data`, `payload` vẫn có — đúng mục đích fixture.

### 4.2 Target tạm `fakechat-strict` — mặc định an toàn

Tạo target tạm cùng script nhưng bỏ 2 key (mặc định rỗng/false), chạy 1 lượt:

```text
run 20261025T132011Z-fakechat-strict  status=completed
POST /backend-api/conversation?turn=1  body? False  request_body? False
sse entries 3  raw? False  (data_bytes + data_sha256)
ws  entries 2  raw? False  (payload_bytes + payload_sha256)
```

Target tạm đã xóa sau replay; chỉ còn artifact dưới `data/output/` (gitignored).

### 4.3 ChatGPT — ca chính

Run trước khi sửa probe: `20261025T132414Z-chatgpt`

```text
requests 50 · matched ... · sse 0 · ws 2
raw CDP request/response body: 0
sensitive headers: 91 → toàn bộ "[redacted]"
raw probe bodies: 8 (sample ~201 ký tự)   ← gap
```

Run sau khi sửa probe: `20261025T133736Z-chatgpt`

```text
status completed · steps 6/6 · requests 18 · matched 13 · sse 0 · ws 2
exceptions 0 · console_errors 0
raw CDP request/response body: 0
raw sse/ws: 0 / 0
sensitive headers: 43 → toàn bộ "[redacted]"
probe.network: 12 entry · raw body 0 · body_redacted 7
```

Kết luận: policy hoạt động trên cả CDP và probe. Không còn prompt/body sample trong
artifact của run mới.

### 4.4 Sự cố replay

Lần chạy lại đầu tiên fail ở setup `new_chat` step 1 (`wait_hidden` assistant h4) sau
30 s: click `New chat` không điều hướng, trang vẫn ở `/c/{id}`. Click thủ công bằng
`web click chatgpt 'button[aria-label="New chat"]'` thành công; chạy lại thì pass.

Đây là flake "click rơi vào overlay/route chưa sẵn sàng", đã có trong playbook. Chưa
sửa chain vì chưa đủ bằng chứng lặp lại; ghi nhận để Phase 12 quyết định.

## 5. Artifact cũ

Các run trước Phase 10 (`20261025T115728Z`, `20261025T115909Z`) vẫn chứa response body
cho `/backend-api/system_hints` vì lúc đó `network_patterns` bật body capture. Chúng nằm
dưới `data/output/` (gitignored), không phải tài liệu. Lệnh quét:

```bash
rg -n 'Cookie: |Authorization: |"payloadData"|sk-[A-Za-z0-9]' docs/skills data/output/web
```

vẫn khớp `sk-proj` trong body cũ (là keyword trong system hints, không phải credential).
Run mới không khớp. Đề xuất: xóa các run cũ khi không còn cần đối chiếu, hoặc chấp nhận
vì đã gitignore; không tự xóa vì báo cáo Phase 8/9 đang tham chiếu số liệu.

## 6. Sai lệch so với kế hoạch

1. Thêm `application/probe_network_redaction.py` ngoài bảng file Phase 10 vì phát hiện
   probe lưu body sample. Không sửa Rust `wre-probe`.
2. `body_capture_patterns` áp cho cả CDP response body, CDP request body, và probe body
   sample; `network_patterns` chỉ còn là bộ lọc summary.

## 7. Lệnh verify

```bash
uv run python -m unittest discover -s tests          # 134 pass
uv run aio-reverse web run fakechat ...               # raw fixture giữ nguyên
uv run aio-reverse web run chatgpt ...                # 0 raw body/stream, 43 header redacted
uv run aio-reverse web state chatgpt                  # profile bền, không cần login lại
```

Không commit.
