# Báo cáo nghiệm thu — Phase 4: Tách CDP adapter + `drain_probe`

Ngày: 2026-10-25

## 1. Mục tiêu task

Tách `adapters/web/chrome_cdp_adapter.py` (1066 dòng) thành package `adapters/web/cdp/` theo từng trách nhiệm, hợp nhất hai đường dump probe cũ thành một `drain_probe()` gọi `window.__WRE.drain()`, đồng thời bổ sung `list_pages()` và mở rộng `press()` cho đủ 4 phím action script.

## 2. Đã làm được gì (chi tiết thay đổi)

- Tách module:
  - `websocket_transport.py`: protocol `WsTransport` + `WebSocketTransport`.
  - `cdp_channel.py`: `CdpChannel` (reader thread, pending map, timeout, lỗi loud).
  - `page_targets.py`: `http_json`, `list_page_targets`, `open_page_target`, `select_page` (exact → prefix → fallback).
  - `turn_collector.py`: gom Network/SSE/WebSocket/console/exception theo lượt.
  - `response_bodies.py`: `collect_bodies` + cap 4 MiB.
  - `chrome_cdp_session.py`: `ChromeCdpSession`, trusted input, `drain_probe`, `list_pages`.
  - `cdp_values.py` (bổ sung): các accessor CDP dùng chung giữa collector và session, tránh lặp logic.
- `drain_probe()` thay `dump_wre()`/`dump_python_probe()`: gọi một biểu thức duy nhất chứa `__WRE.drain()`; nếu `__WRE` không tồn tại hoặc không phải object → `ProbeUnavailableError` (fail loud).
- `IBrowserSessionPort`: bỏ 2 method dump phân mảnh, thêm `drain_probe()` và `list_pages()`.
- `list_pages()` trả các page target từ `/json/list`; chưa `attach()` → `BrowserSessionError`.
- `press()` hỗ trợ `Enter`, `Escape`, `Tab`, `Backspace`:
  - `Enter` gửi `keyDown` kèm `text="\r"`;
  - `Escape`/`Tab`/`Backspace` gửi `rawKeyDown`;
  - phím khác → `ValueError` kèm danh sách hợp lệ.
- Xóa `adapters/web/chrome_cdp_adapter.py`; cập nhật `adapters/web/__init__.py` và import trong `experiments/chatgpt.py`.
- `tests/test_cdp_routing.py` chuyển sang import package mới; thêm test cho `drain_probe` (có/không có probe), `list_pages` chưa attach, `press` Enter/Escape và phím bị từ chối.

## 3. Làm tại đâu (file & vị trí)

| File | Nội dung |
|---|---|
| `src/aio_reverse/adapters/web/cdp/__init__.py` | Export công khai của package |
| `src/aio_reverse/adapters/web/cdp/websocket_transport.py` | `WsTransport`, `WebSocketTransport` |
| `src/aio_reverse/adapters/web/cdp/cdp_channel.py` | `CdpChannel`, `_Pending`, `_error_text` |
| `src/aio_reverse/adapters/web/cdp/page_targets.py` | HTTP DevTools, `list_page_targets`, `open_page_target`, `select_page` |
| `src/aio_reverse/adapters/web/cdp/turn_collector.py` | `TurnCollector` |
| `src/aio_reverse/adapters/web/cdp/response_bodies.py` | `MAX_BODY_BYTES`, `collect_bodies` |
| `src/aio_reverse/adapters/web/cdp/chrome_cdp_session.py` | `ChromeCdpSession`, `KEY_SPECS`, `drain_probe`, `list_pages` |
| `src/aio_reverse/adapters/web/cdp/cdp_values.py` | Accessor giá trị CDP dùng chung |
| `src/aio_reverse/application/ports/browser_session_port.py` | Bỏ dump phân mảnh; thêm `drain_probe`, `list_pages` |
| `src/aio_reverse/adapters/web/__init__.py` | Import từ `.cdp` |
| `src/aio_reverse/experiments/chatgpt.py` | Import `ChromeCdpSession` từ package mới |
| `tests/test_cdp_routing.py` | Import mới + 5 test bổ sung |

## 4. Hướng dẫn và kết quả verify

Lệnh:

```bash
cd /data/projects/web-apps/aio_reverse
uv run python -m unittest tests.test_cdp_routing -v
```

Kết quả:

```text
Ran 28 tests in 0.084s

OK
```

Chạy toàn bộ suite Python:

```bash
uv run python -m unittest discover -s tests
```

Kết quả:

```text
Ran 108 tests in 0.542s

OK
```

Ghi chú:
- Phase này bổ sung `cdp_values.py` ngoài 6 module dự kiến để tránh lặp accessor giữa collector và session; đã ghi vào mục 8 `docs/plans.md`.
- `drain_probe()` fail loud khi thiếu probe thay vì trả `None`; đường chạy chính (Phase 5) sẽ inject probe và verify `__WRE` trước khi gọi.
- `flow_runner.py` (legacy) vẫn còn dùng tên dump cũ trên fake session của test; file này sẽ bị xóa ở Phase 7.
