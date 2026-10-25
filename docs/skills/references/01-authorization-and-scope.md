# 01 — Hợp đồng nhiệm vụ, quyền và dữ liệu

Mục đích: chốt "được làm gì" trước khi mở trình duyệt. Bỏ qua file này là nguyên nhân
phổ biến nhất của recon sai phạm vi, thu thập quá nhiều, hoặc vô tình thực hiện hành
động không thể hoàn tác.

## 1. Mission contract

Điền trước khi chạy bất kỳ lệnh nào:

```text
Goal:            <một câu, kết quả quan sát được>
Target:          <origin + route>
Account:         <tài khoản nào, ai sở hữu/cho phép>
Allowed:         <mở, đọc DOM, gõ, gửi, tải?>
Forbidden:       <mua, xóa, đổi quyền, gửi tiền, spam, scrape hàng loạt?>
Evidence:        <artifact + trường cụ thể chứng minh thành công>
Stop:            <điều kiện dừng>
Time/rate budget <số lượt, số phút, khoảng cách giữa các lượt>
```

Nếu người dùng không nêu, mặc định an toàn:

- Chỉ đọc DOM/network metadata.
- Chỉ thực hiện hành động không phá hủy, có thể lặp lại.
- Một vài lượt thử, không tải hàng loạt.
- Dừng khi gặp dữ liệu nhạy cảm, CAPTCHA, cảnh báo vi phạm, hoặc trang yêu cầu quyền
  mới.

## 2. Ranh giới tuyệt đối

| Không làm | Vì sao |
|---|---|
| Tự động đăng nhập, lấy cookie/token | Vi phạm quy ước dự án; credential không được lưu |
| Vượt CAPTCHA, anti-bot, paywall | Không phải recon hợp lệ |
| Gửi request hàng loạt để dò endpoint | Có thể là tấn công/DoS |
| Ghi body, prompt thật, nội dung hội thoại vào docs | Rò dữ liệu |
| Dùng `evaluate` để vá DOM hoặc giả lập kết quả | Che lỗi, làm sai bằng chứng |
| Reload/navigate để che lỗi auth | Có thể che mất nguyên nhân thật |
| Commit `data/profiles/`, `data/output/` | Dữ liệu phiên và artifact cục bộ |

## 3. Phân loại dữ liệu

| Loại | Ví dụ | Được ghi vào docs? |
|---|---|---|
| Metadata giao thức | method, path, status, body_bytes, timing | Có, sau khi bỏ query/ID |
| Tên endpoint | `/backend-api/conversation` | Có |
| Schema suy ra | "response có trường `id` và `title`" | Có, không kèm giá trị |
| Giá trị thật | email, ID hội thoại, token | Không |
| Body/prompt/nội dung | JSON request/response, câu trả lời | Không |
| Cookie/profile | file trong `data/profiles/` | Không |

Quy tắc redaction khi viết báo cáo:

- Bỏ query string, fragment.
- Thay UUID/ID dài bằng `{id}`.
- Không dán URL đầy đủ có token.
- Không dán ảnh chụp màn hình có thông tin tài khoản.

## 4. Điều kiện dừng

Dừng ngay và báo người dùng khi:

1. Phiên đăng nhập mất hoặc trang chuyển sang login.
2. Xuất hiện CAPTCHA, challenge lạ, hoặc thông báo giới hạn.
3. Hành động tiếp theo có thể mua/xóa/gửi ra bên ngoài/đổi quyền.
4. Dữ liệu quan sát được vượt phạm vi mission (ví dụ thấy thông tin người khác).
5. Ba lần timeout liên tiếp ở cùng một bước với cùng một lỗi.
6. Selector gãy mà không thể sửa bằng cấu hình target.

Không "thử thêm một lần" bằng cách đổi tài khoản, đổi IP, hoặc tắt các lớp bảo vệ.

## 5. Hợp đồng bằng chứng

Báo cáo chỉ được khẳng định điều có artifact hoặc lệnh tái lập:

| Mức | Cách ghi |
|---|---|
| Observed | "Đã thấy trong run `<id>`: `probe.network` có 4 POST tới path X" |
| Inferred | "Suy ra X là bước chuẩn bị lượt, dựa trên thứ tự và tên path" |
| Unknown | "Chưa xác định được X; cần thêm một lượt đo có kiểm soát" |

Không dùng từ "chắc chắn", "luôn luôn", "hệ thống dùng React" nếu chưa có bằng chứng
trực tiếp. Hành vi SPA có thể quan sát mà không cần biết framework.

## 6. Checklist trước khi mở Chrome

- [ ] Mission contract đã điền.
- [ ] Tài khoản thuộc quyền hoặc được phép.
- [ ] Biết hành động nào bị cấm.
- [ ] Biết artifact nào sẽ dùng làm bằng chứng.
- [ ] Biết điều kiện dừng.
- [ ] Không có credential trong prompt, shell history, hay file cấu hình.
- [ ] Đã xác nhận `data/profiles/` và `data/output/` được gitignore.
