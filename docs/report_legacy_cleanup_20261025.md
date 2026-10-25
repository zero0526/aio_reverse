# Report — Phase 7: dọn kiến trúc cũ & cập nhật tài liệu (2026-10-25)

## 1. Mục tiêu

Kết thúc Phase 7 của `docs/plans.md`:

- Xóa toàn bộ module/test của kiến trúc `ProbeMode` / `TurnSpec` / `FlowRunner` /
  `CHAT_PROBE_JS` (8 module/dir cùng 3 test cũ) để repo chỉ còn một đường chạy duy nhất:
  Rust probe + action script JSON.
- Cập nhật `README.md` và `docs/capture_analystic.md` theo kiến trúc mới.
- Xác nhận không còn symbol cũ trong `src/` và `tests/`, toàn bộ test pass sau khi xóa.

## 2. Thay đổi

### 2.1 Xóa module kiến trúc cũ

| File / thư mục | Lý do |
|---|---|
| `src/aio_reverse/adapters/web/flow_runner.py` | Thay bằng `InteractiveSession` + `ActionEngine` |
| `src/aio_reverse/application/ports/web_flow_port.py` | Thay bằng `application/ports/web_session_port.py` |
| `src/aio_reverse/application/use_cases/run_web_flow.py` | Thay bằng `run_web_scripts.py` |
| `src/aio_reverse/infrastructure/artifacts/legacy_run_store.py` | Store tạm cho test cũ |
| `src/aio_reverse/targets/base.py` | Thay bằng `targets/web_target.py` + JSON |
| `src/aio_reverse/targets/chatgpt.py` | Thay bằng `targets/chatgpt/target.json` |
| `src/aio_reverse/experiments/` (`chatgpt.py`, `__init__.py`) | Thay bằng `aio-reverse web ...` |
| `src/aio_reverse/adapters/mcp/tools.py` | Thay bằng `server.py` + `session_registry.py` + `web_tools.py` |

### 2.2 Xóa test cũ

| File | Ghi chú |
|---|---|
| `tests/test_targets.py` | Test `ProbeMode`/`TurnSpec`/`WebPageSpec` |
| `tests/test_flow_runner.py` | Test `FlowRunner` |
| `tests/test_run_web_flow.py` | Test use case cũ |

### 2.3 Cập nhật code

- `src/aio_reverse/targets/__init__.py`: chỉ còn docstring mô tả package dữ liệu target.
- `src/aio_reverse/application/ports/__init__.py`: export `IRunStore`, `IWebSession`,
  `RunPaths`, `SessionTurn`, `StepRecord` từ `web_session_port`.
- `src/aio_reverse/application/use_cases/__init__.py`: export `RunResult`,
  `RunWebScriptsUseCase`.
- `src/aio_reverse/domain/errors.py`: giữ `ActionScriptError`.
- `src/aio_reverse/infrastructure/config.py`: giữ `targets_root`, `profiles_dir`,
  `profile_dir`, `web_output_dir`; bỏ cấu hình profile tạm.
- `.gitignore`: giữ `data/workspace/`, `data/profiles/`, `data/output/`.

### 2.4 Cập nhật tài liệu

- `README.md`: kiến trúc mới, quickstart `web targets/scripts/login/run/state`, 11 MCP tool,
  hướng dẫn thêm target, cảnh báo chỉ dùng tài khoản được phép/ToS.
- `docs/capture_analystic.md`: viết lại theo kiến trúc hiện tại, bản đồ code kèm số dòng,
  artifact layout mới, mục 7 liệt kê từng thành phần cũ và thành phần thay thế.
- `docs/plans.md`: tick Phase 7, cập nhật trạng thái tổng quan, thêm nhật ký và sai lệch.

## 3. Vị trí file chính

| Nội dung | Vị trí |
|---|---|
| Action engine | `src/aio_reverse/application/action_engine.py` |
| Session sống lâu | `src/aio_reverse/application/interactive_session.py` |
| Use case mới | `src/aio_reverse/application/use_cases/run_web_scripts.py` |
| Artifact store mới | `src/aio_reverse/infrastructure/artifacts/run_store.py` |
| Target schema | `src/aio_reverse/targets/web_target.py` |
| Target dữ liệu | `targets/chatgpt/target.json` + `targets/chatgpt/scripts/*.json` |
| CLI | `src/aio_reverse/cli/*.py` + `src/aio_reverse/main.py` |
| MCP | `src/aio_reverse/adapters/mcp/{server,session_registry,web_tools}.py` |
| Tài liệu kiến trúc | `docs/capture_analystic.md` |

## 4. Kiểm chứng

### 4.1 Không còn symbol cũ

```bash
rg "ProbeMode|TurnSpec|CHAT_PROBE_JS|dump_wre|dump_python_probe|probe-python|FlowRunner|RunWebFlowUseCase|web_flow_port|flow_runner|targets\.base|targets\.chatgpt" src tests
```

Kết quả thực tế: không có dòng khớp (exit 1).

### 4.2 Full Python test suite

```bash
uv run python -m unittest discover -s tests
```

Kết quả thực tế:

```text
Ran 112 tests in 0.303s

OK
```

Phân bổ: target 11, action script 29, toolkit 15, CDP 28, action engine 5,
interactive session 8, use case 5, MCP 11.

### 4.3 Rust test suite

```bash
cd libs/web-re-toolkit
cargo test -p wre-probe -p wre-target -p wre-cli
```

Kết quả thực tế:

```text
running 5 tests  ... test result: ok. 5 passed
running 10 tests ... test result: ok. 10 passed
running 9 tests  ... test result: ok. 9 passed
```

Tổng: 24 test Rust pass (wre-probe 15, wre-target/wre-cli 9).

### 4.4 CLI smoke

```bash
uv run aio-reverse web targets
uv run aio-reverse web scripts chatgpt
```

Kết quả thực tế:

```text
chatgpt	https://chatgpt.com/	port 9445
setup	new_chat	Open a fresh conversation before the measured turn
turn	send_prompt	Type one prompt, send it and wait for the streamed reply to settle
```

### 4.5 Việc chưa làm trong Phase 7

- Chưa chạy E2E Chrome/ChatGPT thật; thuộc Phase 8.
- Chưa thêm fixture chat giả; thuộc Phase 8.
