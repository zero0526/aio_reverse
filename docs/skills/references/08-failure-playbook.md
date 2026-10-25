# 08 — Playbook khi chain gãy

Mục đích: chẩn đoán theo bằng chứng, không đoán và không che lỗi.

## 1. Nguyên tắc

1. Đọc lỗi trước, đọc `steps.json`/`run.json` sau.
2. Xác định lỗi thuộc **trạng thái**, **selector**, **input**, **network**, hay
   **stream**.
3. Chạy lại đúng một bước bằng handover để thu hẹp.
4. Nếu lỗi do môi trường (phiên, hydration), sửa môi trường; không sửa chain để che.
5. Nếu lỗi do DOM/network đổi, cập nhật target/script và ghi lại bằng chứng.
6. Không tự động retry mù nhiều lần; có thể vi phạm rate limit hoặc làm sai dữ liệu.

## 2. Bảng chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Chẩn đoán | Xử lý |
|---|---|---|---|
| `wait_visible` timeout, selector khớp 0 | DOM chưa render, selector sai, sai route | `web evaluate` đếm raw/rendered | Chờ đúng state; cập nhật selector |
| Selector khớp > 0 nhưng rendered = 0 | Bản sao `display:none` / route cache | Kiểm tra ancestor, `getComputedStyle` | Dùng container hẹp + visibility-aware action |
| Count tăng nhưng UI không đổi | Đếm bản ẩn | So raw/rendered | Count delta + rendered filter |
| Click không có hiệu ứng | Overlay che, pointer-events, element không nhận click | `elementFromPoint` tại tâm | Ghi gap; chờ overlay biến mất; không xóa overlay |
| `web type` không vào chỗ | Chưa focus đúng element | `document.activeElement` | Click đúng composer trước; dùng action `type` |
| Send click nhưng không gửi | Nút disabled hoặc text chưa vào | Kiểm tra `disabled`, giá trị composer | Chờ enable; kiểm tra input |
| Login timeout | Hết phiên, sai `login_expression` | `web state`, kiểm tra landmark | `web login` lại bằng tay |
| Ready timeout ngay sau restart | SPA chưa hydrate | `readyState`, skeleton | Chờ thêm; reload có kiểm soát; ghi caveat |
| `ProbeUnavailableError` | Navigate làm mất `__WRE`, CSP chặn, init script lỗi | `typeof window.__WRE` | `web inject_probe`; kiểm tra CSP/init script |
| `exceptions` tăng sau lượt | Env capture gọi getter trả promise; lỗi hydration; script trang | Đọc `exceptions.json` | Sửa primitive/env; không bỏ qua |
| `wait_network_quiet` timeout | Polling/telemetry nền | Xem request lặp trong `network.json` | Lọc pattern hoặc dùng tín hiệu UI |
| UI xong nhưng network còn | Stream chunk cuối | `probe.network` + timings | Chờ thêm hoặc chấp nhận tín hiệu UI |
| `sse=0` ngoài dự kiến | Stream bằng fetch, hoặc hook tắt | Kiểm tra `probe.network`, POST stream | Không kết luận vội; xác định transport |
| `ws_frames=0` nhưng có WebSocket | Frame đến sau `end_turn` | Timings, probe websocket | Chờ tín hiệu UI/network trước khi kết thúc |
| Method `null` trong network | Request bắt đầu trước `begin_turn` (`orphan`) | Xem `orphan` | Không suy ra method; mở rộng cửa sổ capture nếu cần |
| `body_bytes=null` cho POST chính | Response stream/chunked | `probe.network`, WS | Bình thường với stream; không phải lỗi |
| Chrome/CDP không kết nối | Port bận, Chrome crash, profile lock | `web session`, `websocket` | Dừng Chrome đúng cách; đổi port/profile |
| `wre binary not found` | Chưa build hoặc `WRE_BIN` sai | `wre --version` | Build release hoặc đặt `WRE_BIN` |
| Target load lỗi | Unknown key, sai URL, thiếu script | Thông điệp validator | Sửa JSON; không try/except |
| MCP session cũ | Session registry giữ session chết | Gọi `web_close`, mở lại | Không dùng chung session giữa target |
| Artifact không có `turn-NN` | Run fail trước khi ghi turn | `run.json.status` | Đọc lỗi gốc, chạy lại |
| `script timeout_s` không chặn | Engine chưa enforce timeout cấp script | Kiểm tra từng action | Đặt timeout từng action; ghi gap |

## 3. Quy trình chẩn đoán 5 bước

```text
1. Đọc run.json → status, error, script, variables
2. Đọc steps.json → bước cuối cùng chạy được
3. Chạy handover đúng bước → xem lỗi tức thời
4. Kiểm tra DOM/network ở trạng thái đó
5. Sửa một biến tại một thời điểm, chạy lại một turn
```

Không sửa nhiều thứ cùng lúc; không đổi selector và timeout và network pattern trong
cùng một lần thử.

## 4. Phân biệt lỗi môi trường và lỗi thiết kế

| Dấu hiệu | Loại | Cách xử lý |
|---|---|---|
| Lần đầu fail, lần hai pass không đổi gì | Môi trường/hydration | Ghi caveat; thêm wait, không thêm retry mù |
| Fail ở mọi lần, cùng selector | Thiết kế/DOM | Cập nhật target/script |
| Fail chỉ khi có dữ liệu cũ | Thiết kế count | Delta count |
| Fail chỉ khi stream dài | Timeout | Tăng timeout theo bằng chứng |
| Fail sau khi đổi network pattern | Cấu hình | Xem lại pattern/body capture |
| Fail sau restart Chrome | Phiên/profile | Kiểm tra login, hydration, port |

## 5. Khi nào dừng và báo gap

- Primitive không xuyên shadow DOM/iframe.
- Cần phím ngoài whitelist.
- Cần upload file / kéo thả / chạm đa điểm.
- Cần đọc response body nhưng `network_patterns` không phù hợp (và không được phép mở).
- Cần vượt CAPTCHA/anti-bot.
- Trang yêu cầu quyền/mua/xác nhận không nằm trong mission.

Ghi gap vào báo cáo với: hiện tượng, primitive thiếu, đề xuất bổ sung, rủi ro nếu bổ
sung. Không tự ý thêm code engine trong lúc recon.

## 6. Checklist sau khi sửa

- [ ] Lỗi gốc được nêu, không chỉ triệu chứng.
- [ ] Sửa tối thiểu, đúng một nguyên nhân.
- [ ] Chạy lại turn đo, không chỉ handover.
- [ ] Artifact chứng minh sửa đúng.
- [ ] Không có retry mù/fallback im lặng được thêm vào.
- [ ] Báo cáo/`docs/plans.md` được cập nhật nếu hành vi thay đổi.
