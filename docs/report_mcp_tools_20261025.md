# Báo cáo Phase 6 — MCP tools và session registry

## 1. Mục tiêu

Cho agent giao tiếp với các web target qua MCP local stdio, dùng lại đúng lớp
`InteractiveSession`/`RunWebScriptsUseCase` của Phase 5, giữ Chrome sống giữa các
lần gọi và đóng session an toàn khi server dừng.

## 2. Thay đổi chính

| Hạng mục | Thay đổi |
|---|---|
| Session registry | `SessionRegistry` giữ tối đa một session mỗi target, khóa việc tạo session trùng, `close` trả `False` nếu chưa mở, `close_all` đóng hết rồi báo lỗi đầu tiên kèm cause. |
| Tool services | `WebToolServices` bọc target registry, store, session registry và script loader; không tự mở Chrome khi khởi tạo server. |
| 11 tool | `web_targets`, `web_open`, `web_run_script`, `web_state`, `web_inject_probe`, `web_click`, `web_type`, `web_press`, `web_evaluate`, `web_navigate`, `web_close`. |
| Server | `MCPServer("aio-reverse")` (MCP 2.x), chạy stdio, `finally: sessions.close_all()`. Xóa skeleton `tools.py` cũ. |
| Composition | Chuyển helper dựng config/toolkit/registry/store/session sang `src/aio_reverse/composition.py` để CLI và MCP dùng chung. |
| Close semantics | `web_close` mặc định giữ Chrome để giữ đăng nhập; `keep_browser=false` mới dừng Chrome. |

## 3. Vị trí file

| File | Vai trò |
|---|---|
| `src/aio_reverse/adapters/mcp/session_registry.py` | Registry session sống lâu |
| `src/aio_reverse/adapters/mcp/web_tools.py` | Services + đăng ký 11 tool |
| `src/aio_reverse/adapters/mcp/server.py` | Build/run MCP server, cleanup |
| `src/aio_reverse/adapters/mcp/__init__.py` | Export `WebMcpServer`, `build_server` |
| `src/aio_reverse/composition.py` | Composition root dùng chung CLI/MCP |
| `src/aio_reverse/cli/*.py` | Cập nhật import composition root |
| `src/aio_reverse/main.py` | `mcp` và không tham số → `build_server().run()` |
| `tests/test_mcp_tools.py` | 11 test registry/tool/stdio wiring |
| (`đã xóa`) `src/aio_reverse/adapters/mcp/tools.py` | Skeleton JSON schema cũ |

## 4. Lệnh verify và output thực tế

```text
$ uv run python -m unittest discover -s tests
............................................................................................................................................
----------------------------------------------------------------------
Ran 140 tests in 0.651s

OK
```

Smoke qua MCP client stdio (`initialize` → `tools/list` → `web_targets`):

```text
11 ['web_targets', 'web_open', 'web_run_script', 'web_state', 'web_inject_probe', 'web_click', 'web_type', 'web_press', 'web_evaluate', 'web_navigate', 'web_close']
{
  "targets": [
    {
      "name": "chatgpt",
      "entry_url": "https://chatgpt.com/",
      ...
```

Không có Chrome/target nào bị mở trong smoke này; `web_targets` chỉ đọc JSON.
