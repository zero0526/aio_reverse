# Báo cáo Phase 5 — ActionEngine, InteractiveSession, artifact và CLI

## 1. Mục tiêu

Hoàn thiện lớp Python mỏng để điều khiển một web target qua Chrome CDP và probe
Rust đã có, thay cho flow hardcode cũ:

- Chạy action script JSON có template runtime, ghi lại từng bước.
- Giữ một phiên Chrome sống lâu với profile bền, inject probe Rust một lần và
  `drain()` mỗi lượt.
- Ghi artifact đầy đủ cho từng lượt và summary của run.
- Cung cấp CLI cho người dùng và agent handover.

## 2. Thay đổi chính

| Hạng mục | Thay đổi |
|---|---|
| Thực thi action | `ActionEngine` resolve template theo từng bước, lưu biến `save`, bọc lỗi trong `ActionScriptError` kèm script/step/type. Action `type` click selector để focus trước khi chèn text. |
| Chờ trang | `ExpressionWaiter` poll `wait_visible`, `wait_hidden`, `count`, `wait_count`, `wait_network_quiet`; timeout fail loud. |
| Phiên tương tác | `InteractiveSession.open()` start Chrome với `--profile`, attach, navigate nếu lệch origin, chờ ready, kiểm tra đăng nhập, emit probe Rust + init script, verify `__WRE`. `run_script()` chạy begin_turn → actions → `drain_probe()` → page/env → end_turn. |
| Handover | `click`, `type_text`, `press`, `evaluate`, `navigate`, `inject_probe`, `dump_state`, `close(keep_browser=True)`. |
| Use case | `RunWebScriptsUseCase`: setup script không ghi artifact, turn script ghi artifact; lỗi đăng nhập/lỗi lượt đều ghi `run.json` failed rồi re-raise; luôn đóng session. |
| Artifact | `run.json`, `summary.json`, `turn-NN/{request,steps,probe,network,sse,websocket,console,exceptions,env,page,timings}.json`. |
| Toolkit | `emit_probe()` gọi `wre probe emit`; `start_browser`/`capture` nhận `--profile`; validate JSON `{name,source,bytes}`. |
| CLI | `aio-reverse web targets|scripts|probe|login|run|session|state|click|type|press|evaluate|navigate`, `mcp`; không tham số chạy MCP. |
| Test | Fake `wre` hỗ trợ `probe emit` + `--profile`; thêm test engine, session, use case, toolkit. |

## 3. Vị trí file

| File | Vai trò |
|---|---|
| `src/aio_reverse/application/action_engine.py` | Thực thi một `ActionScript`, trả `StepRecord` |
| `src/aio_reverse/application/expression_waiter.py` | Poll điều kiện trang, timeout fail loud |
| `src/aio_reverse/application/interactive_session.py` | Ghép target + toolkit + CDP session |
| `src/aio_reverse/application/turn_summary.py` | Summary lượt/run dùng cho artifact |
| `src/aio_reverse/application/ports/web_session_port.py` | `IWebSession`, `IRunStore`, `SessionTurn`, `StepRecord`, `RunPaths` |
| `src/aio_reverse/application/use_cases/run_web_scripts.py` | Use case setup + turn scripts |
| `src/aio_reverse/infrastructure/artifacts/run_store.py` | Ghi artifact JSON |
| `src/aio_reverse/adapters/toolkit/wre_cli.py` | `emit_probe`, profile, validate output |
| `src/aio_reverse/cli/composition.py` | Dựng config/toolkit/registry/store/session |
| `src/aio_reverse/cli/web_targets.py` | `web targets`, `web scripts` |
| `src/aio_reverse/cli/web_probe.py` | `web probe` in JS của Rust |
| `src/aio_reverse/cli/web_login.py` | `web login` human-in-the-loop |
| `src/aio_reverse/cli/web_run.py` | `web run`, parse `--var` |
| `src/aio_reverse/cli/web_handover.py` | `session/state/click/type/press/evaluate/navigate` |
| `src/aio_reverse/main.py` | Parser, dispatch, fallback MCP |
| `tests/test_action_engine.py` | 5 test engine |
| `tests/test_interactive_session.py` | 8 test session |
| `tests/test_run_web_scripts.py` | 5 test use case + artifact |
| `tests/test_wre_cli.py` | Thêm 3 test emit probe/profile |
| `tests/fixtures/fake_wre.py` | Hỗ trợ `probe emit` |

## 4. Lệnh verify và output thực tế

```text
$ uv run python -m unittest discover -s tests
...............................................................................
----------------------------------------------------------------------
Ran 129 tests in 0.602s

OK
```

```text
$ uv run aio-reverse web targets
chatgpt	https://chatgpt.com/	port 9445

$ uv run aio-reverse web scripts chatgpt
setup	new_chat	Open a fresh conversation before the measured turn
turn	send_prompt	Type one prompt, send it and wait for the streamed reply to settle
```

```text
$ uv run aio-reverse web probe chatgpt > /tmp/aio-probe-chatgpt.js
$ wc -c /tmp/aio-probe-chatgpt.js
19494 /tmp/aio-probe-chatgpt.js
$ node --check /tmp/aio-probe-chatgpt.js && echo NODE_OK
NODE_OK
```

Chưa chạy `web run` với Chrome/ChatGPT thật trong phase này; việc đó nằm ở
Phase 8 (cần đăng nhập thủ công).
