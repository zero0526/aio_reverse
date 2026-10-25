# AGENTS.md — explore

Rules chi tiết: xem `.agent/agent-rules.md`. Các quy tắc sau là **bắt buộc tuyệt đối**:

1. **Fail loud — cấm trả default khi có lỗi.** Không `catch` nuốt lỗi, không fallback `null`/`{}`/`[]`/`0` âm thầm. Luôn `throw` exception kèm ngữ cảnh (thao tác, input, bước) và giữ `cause` gốc để trace được stack. Chỉ fallback khi người dùng yêu cầu rõ ràng.
2. **DRY — một logic chỉ viết tại MỘT nơi duy nhất.** Trước khi viết hàm mới phải kiểm tra dự án đã có hàm/util tương đương chưa. Phát hiện lặp logic ≥ 2 lần → extract thành util/const dùng chung, import từ một nguồn.
3. **Một file - Một logic duy nhất, cấm file thập cẩm:** Không nhét nhiều nghiệp vụ không liên quan vào một file dài ngoằng. Mỗi file chỉ tập trung cho 1 trách nhiệm/logic cụ thể. Tên file phải tự tường minh (nhìn tên biết ngay bên trong định nghĩa phần logic nào, cấm đặt tên chung chung vô nghĩa như `utils`, `helper`, `misc`, `common`).
4. **Không speculation:** không abstraction cho tương lai, không code chết, không xử lý lỗi cho trường hợp không thể xảy ra.
5. **Vi phạm trong phạm vi đang sửa → báo ngay kèm đề xuất sửa**, không im lặng bỏ qua.
6. **Báo cáo nghiệm thu tại `docs/` sau mỗi task:** Sau khi làm xong bất kỳ task nào, bắt buộc tạo một file báo cáo mới tại `docs/report_<tên_task>_<YYYYMMDD>.md` nêu rõ: đã làm gì, làm tại đâu (danh sách file & vị trí), lệnh verify và kết quả chạy thực tế để người dùng kiểm chứng. Đồng thời cập nhật trạng thái trong `docs/plans.md`. Cấm báo xong việc chỉ bằng lời nói suông.
