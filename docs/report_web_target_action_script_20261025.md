# Báo cáo nghiệm thu — Phase 3: Python target.json + action script

> Cập nhật 2026-10-25: selector ChatGPT trong báo cáo này là bản chưa xác nhận.
> DOM thật đã đổi; xem bảng selector đã xác nhận tại `targets/chatgpt/README.md`
> và `docs/report_chatgpt_e2e_20261025.md`.

Ngày: 2026-10-25

## 1. Mục tiêu task

Thay lớp mục tiêu hardcode (`targets/base.py`, `targets/chatgpt.py`) bằng cấu hình JSON tại repo-root `targets/<name>/`, và thay `TurnSpec` bằng action script JSON có template biến. Python chỉ đọc/validate cấu hình; Rust vẫn là nơi duy nhất sở hữu probe.

## 2. Đã làm được gì (chi tiết thay đổi)

- Schema target mới:
  - `TargetProbeConfig`: `preset` (`fingerprint|minimal|none`), `properties`, `methods`, `events`, `network`, `workers`, `stealth`, `call_sites`, `sse`, `websocket`; mặc định bật toàn bộ trap/probe.
  - `WebTargetSpec`: URL entry/login bắt buộc http(s), biểu thức login/ready, `network_patterns`, `env_depth`, `chrome_port`, danh sách `setup_scripts`/`turn_scripts`, `probe`.
  - `script_path(name)` trả đường dẫn `scripts/<name>.json` (không tự tạo file).
- Loader/registry:
  - `target_loader.load_target(directory)` đọc JSON strict, từ chối key lạ, tên target phải khớp tên thư mục, và kiểm tra mọi script được khai báo có tồn tại.
  - `target_registry.TargetRegistry(root)` liệt kê target có `target.json`, `resolve(name)` chặn path traversal và báo danh sách target đã biết khi tên sai.
- Action script:
  - 11 action type: `navigate`, `click`, `type`, `press`, `wait_visible`, `wait_hidden`, `count`, `wait_count`, `wait_network_quiet`, `sleep`, `evaluate`.
  - Mỗi type có whitelist field riêng; field lạ, thiếu field bắt buộc, `ms <= 0`, `timeout_s <= 0`, URL không http(s), `key` ngoài `Enter/Escape/Tab/Backspace`, `save` không phải identifier → fail loud.
  - Template `{{name}}`: loader giữ nguyên template và expose `required_variables()` (bỏ qua biến do `save` của action trước cấp). `resolve_action()` render từng action tại runtime; biến thiếu → lỗi nêu tên, kết quả rỗng → lỗi, `greater_than` không phải số nguyên → lỗi.
  - Placeholder sai định dạng (ví dụ `{{9bad}}`) bị từ chối ngay khi load.
- Target mẫu `targets/chatgpt/`:
  - `target.json`: entry/login `https://chatgpt.com/`, port 9445, setup `new_chat`, turn `send_prompt`, probe fingerprint đầy đủ.
  - `scripts/new_chat.json`: tạo chat mới, chờ `#prompt-textarea`.
  - `scripts/send_prompt.json`: đếm reply trước, nhập `{{prompt}}`, gửi, chờ số reply tăng, chờ nút stop biến mất, chờ network quiet.
  - `README.md` ghi rõ selector chưa xác nhận trên tài khoản thật và cách dò lại bằng `web state`/`web evaluate`.
- Config: thêm `targets_root`, `profiles_dir`, `profile_dir(name)`; `.gitignore` thêm `data/profiles/`.

## 3. Làm tại đâu (file & vị trí)

| File | Nội dung |
|---|---|
| `src/aio_reverse/targets/json_document.py` | Helper JSON strict dùng chung (`load_json_object`, `reject_unknown_keys`, kiểu string/int/number/bool) |
| `src/aio_reverse/targets/web_target.py` | `PROBE_PRESETS`, `require_http_url`, `TargetProbeConfig`, `WebTargetSpec` |
| `src/aio_reverse/targets/target_loader.py` | `load_target`, `TARGET_KEYS`, `PROBE_KEYS`, `_parse_probe` |
| `src/aio_reverse/targets/target_registry.py` | `TargetRegistry.names()` / `resolve()` |
| `src/aio_reverse/targets/action_script.py` | `Action`, `ActionScript`, `parse_action`, `template_names`, `render_templates`, `resolve_action` |
| `src/aio_reverse/targets/action_script_loader.py` | `load_action_script` (validate cấu trúc, không render sớm) |
| `src/aio_reverse/infrastructure/config.py` | `targets_root`, `profiles_dir`, `profile_dir()`; bỏ `targets_dir` |
| `.gitignore` | `data/profiles/` |
| `targets/chatgpt/target.json` | Cấu hình target ChatGPT |
| `targets/chatgpt/scripts/new_chat.json` | Setup script |
| `targets/chatgpt/scripts/send_prompt.json` | Turn script |
| `targets/chatgpt/README.md` | Ghi chú selector và cảnh báo tài khoản/ToS |
| `tests/test_web_target.py` | 11 test loader/registry |
| `tests/test_action_script.py` | 29 test schema/template/runtime resolution |

## 4. Hướng dẫn và kết quả verify

Lệnh:

```bash
cd /data/projects/web-apps/aio_reverse
uv run python -m unittest tests.test_web_target tests.test_action_script -v
```

Kết quả:

```text
Ran 40 tests in 0.004s

OK
```

Kiểm tra target mẫu thực tế:

```bash
uv run python -c "
from pathlib import Path
from aio_reverse.targets.target_loader import load_target
from aio_reverse.targets.action_script_loader import load_action_script
spec = load_target(Path('targets/chatgpt'))
print(spec.name, spec.chrome_port, spec.probe.preset, spec.setup_scripts, spec.turn_scripts)
print(load_action_script(spec, 'new_chat').required_variables())
print(load_action_script(spec, 'send_prompt').required_variables())
"
```

Kết quả:

```text
chatgpt 9445 fingerprint ('new_chat',) ('send_prompt',)
()
('prompt',)
```

Ghi chú sai lệch: template được render tại runtime thay vì load-time vì `send_prompt` dùng biến `replies_before` do chính action `count` phía trước lưu lại. Đã ghi vào mục 8 của `docs/plans.md`. Các module cũ (`targets/base.py`, `targets/chatgpt.py`) vẫn còn để giữ test suite importable và sẽ xóa ở Phase 7.
