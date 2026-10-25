# 10 — Phân tích HTML & AutoCrawl với wre-template

Mục đích: Hướng dẫn Agent và kỹ sư reverse phương pháp phân tích DOM, cắt tỉa boilerplate và tự động suy diễn luật trích xuất (AutoCrawl) cho các trang web mục tiêu, đạt độ chính xác cao và tiết kiệm 70–99% token.

---

## 1. Triết lý AutoCrawl cho Agent

Nếu trang nào cũng gửi nguyên khối raw HTML vào LLM để parse:
- **Tốn token**: Mỗi trang web hiện đại chứa 40,000–100,000 raw tokens. 100 trang sẽ ngốn hàng triệu tokens.
- **Tăng latency**: LLM mất 5–15 giây để đọc và trích xuất từng trang.
- **Bẫy attention**: Hiệu ứng "Lost in the middle" khiến LLM dễ bị xao nhãng bởi boilerplate, banner quảng cáo.

**Quy trình chuẩn (Two-Stage Induction):**
1. **Giai đoạn 1 — Khám phá & Suy diễn (Induction 1 lần):**
   - Lấy 2–3 trang mẫu cùng layout/template.
   - Dùng `wre template` phân tích vi phân (delta-diff) và bóc tách boilerplate.
   - LLM chỉ nhìn vào bản **Skeleton + Slot** gọn gàng để xác nhận ý nghĩa nghiệp vụ (Tiêu đề, Giá, Tác giả, Ngày đăng, Thân bài).
   - Tự động sinh ra bộ **CSS / XPath Selectors** hoặc **Repeater Record Schema**.
2. **Giai đoạn 2 — Crawl tốc độ cao (Zero-Token Execution):**
   - Chạy engine crawler (Rust hoặc Python lxml/scraper) áp dụng trực tiếp các selectors đã sinh.
   - Đạt tốc độ hàng nghìn trang/giây với chi phí **0 token LLM**!

---

## 2. Các công cụ cốt lõi trong `wre template`

### 2.1. Phân tích vi phân đa trang (`wre template diff`)
So sánh trực tiếp $N \ge 2$ trang cùng layout:
- **Thuật toán**: Hash cây bottom-up $O(N)$ bằng `XxHash64`.
- **Cơ chế Dual-Hash**:
  - `hash_raw`: băm text thô và thuộc tính whitelist.
  - `hash_norm`: thế regex cho ngày tháng, số lượng, UUID để nhận diện và cắt tỉa boilerplate giả động (view counter, timestamp render).
- **Lệnh thực thi**:
  ```bash
  # Xuất skeleton phân cấp cho LLM:
  wre template diff page1.html page2.html

  # Xuất kèm XPath trên từng dòng để kiểm chứng:
  wre template diff --xpath page1.html page2.html

  # Tự động tổng hợp CSS/XPath selectors cho từng slot:
  wre template diff --selectors page1.html page2.html

  # JSON có cấu trúc (cho wrapper Python/chương trình):
  wre --json template diff page1.html page2.html
  # → {pages, first_page, reduction_ratio, skeleton, slots[]}
  ```

**Đường Python khỏi gọi `wre` tay** (chuẩn hóa trong `aio-reverse`):

```bash
uv run aio-reverse web snapshot <target> --label home    # outerHTML → data/output/web/<target>/snapshots/
uv run aio-reverse web snapshot <target> --label thread  # trạng thái KHÁC — hai trang giống nhau skeleton vô dụng
uv run aio-reverse web skeleton --page A.html --page B.html --xpath [--json]
```

- Snapshot bị chặn ở 8 MiB (fail loud, không cắt âm thầm), không ghi đè file cùng giây.
- `web skeleton` validate ≥ 2 file `.html` tồn tại trước khi gọi toolkit.
- MCP tương ứng: `web_snapshot`, `web_skeleton` (tổng cộng 13 tool).

### 2.2. Trích xuất trang đơn bằng Mật độ Nội dung (`wre template single`)
Khi chỉ có 1 trang đơn lẻ hoặc cần cô lập nhanh bài viết:
- Sử dụng thuật toán chấm điểm **Text Density** ($\text{text\_len} / \text{tag\_count}$) và **Link Density** ($\text{link\_text} / \text{total\_text}$).
- Tự động phát hiện và loại trừ navigation menus, link-farms (link density $> 0.5$).
- **Lệnh thực thi**:
  ```bash
  wre template single page.html
  # Trả về: Container tag, Text length, Link density, Content score và bản xem trước văn bản
  ```

### 2.3. Khám phá danh sách lặp & Bảng dữ liệu (`wre template repeater`)
Dành cho trang chủ, trang chuyên mục, catalog e-commerce:
- Tự động phát hiện các container có $\ge 3$ phần tử con đồng nhất cấu trúc (`ul > li`, `div > a`, `div.grid > div.card`).
- Khảo sát các trường con bên trong card: Tiêu đề (`title`), Link chi tiết (`url`), Ảnh đại diện (`image`), Thời gian/Giá (`date`/`price`).
- **Lệnh thực thi**:
  ```bash
  wre template repeater category_or_home.html
  # Trả về: Danh sách repeaters, XPath, CSS selectors tương đối cho từng trường, và dữ liệu mẫu
  ```

---

## 3. Case Study Thực tế: Khai phá & Crawl `thanhnien.vn`

Thực nghiệm đo đạc thực tế trên `https://thanhnien.vn/`:

### Bước 1: Khám phá danh mục & bài viết từ Trang chủ
Chạy lệnh khám phá repeaters trên trang chủ:
```bash
wre template repeater home.html
```
**Kết quả thực tế:**
- Phát hiện 26 cấu trúc lặp, trong đó cấu trúc tin tức chính:
  - Container: `ul > li` (18 tin nổi bật).
  - Selector trường:
    - Tiêu đề: `li > a` (text).
    - URL: `li > a` (thuộc tính `href`).
    - Thumbnail: `li > a > img` (thuộc tính `src`).

### Bước 2: Tải 2 bài viết mẫu cùng chuyên mục
```bash
curl -s "https://thanhnien.vn/...-185261025161839363.htm" > article1.html
curl -s "https://thanhnien.vn/...-185261025165110445.htm" > article2.html
```

### Bước 3: Phân tích vi phân và Tự động sinh Selectors
```bash
wre template diff --selectors article1.html article2.html
```
**Kết quả thực tế:**
- **Tỷ lệ cắt tỉa token:** Giảm **99.6%** kích thước văn bản! Toàn bộ thanh `<nav>`, `<footer>`, widget quảng cáo, script theo dõi biến mất.
- **Selectors tự động sinh cho bài viết:**
  - **Tiêu đề bài viết:** `h1 > span` (text).
  - **Chuyên mục:** `article > div > div > a` (text + `href`).
  - **Đoạn dẫn (Sapo):** `div > main > ... > article > div:nth-of-type(3) > div:nth-of-type(1)`.
  - **Các đoạn nội dung:** `article > div:nth-of-type(3) ... > p`.
  - **Chủ đề tag:** `div > main > ... > div:nth-of-type(12) > a` (`href`).

### Bước 4: Kiểm chứng Trang đơn bằng Content Density
```bash
wre template single article1.html
```
**Kết quả thực nghiệm:**
- `Main Content Container: <div>`
- `Link Density: 0.00%` (không có link rác).
- `Text Density: 234.0 chars/tag` (mật độ nội dung đậm đặc).
- `Content Score: 239.0` (vượt trội hoàn toàn so với header/footer).

---

## 4. Cơ chế Tự phục hồi Selector khi DOM thay đổi (Self-Healing)

Khi một trang web đổi giao diện hoặc đổi class CSS (ví dụ Next.js đổi hash class):
1. **Lưu trữ Chữ ký cấu trúc (`ElementFingerprint`)**:
   - Thẻ HTML (`tag`).
   - Chuỗi tổ tiên (`ancestor_tags`: ví dụ `["body", "main", "article"]`).
   - Nhãn ngữ cảnh liền kề (`nearby_label`: ví dụ "Tác giả:", "Giá bán:").
   - Độ dài tối thiểu văn bản.
2. **Thuật toán Khôi phục (`heal_element`)**:
   - Khi selector cũ trả về 0 phần tử, hàm `heal_element` duyệt cây DOM mới và chấm điểm tương đồng:
     - Khớp tag: +0.4.
     - Khớp chuỗi tổ tiên: +0.3.
     - Khớp nhãn liền kề: +0.2.
     - Khớp thuộc tính ngữ nghĩa: +0.1.
   - Nếu điểm $\ge 0.65$, tự động xác định node mới và khôi phục đường dẫn selector mà không làm gãy luồng crawl.
