# Báo cáo nghiệm thu — Crate `wre-template`: Phân tích HTML Delta/Diff-based & Skeleton Extraction

Ngày: 2026-10-25

## 1. Mục tiêu task

Tạo mới crate `wre-template` trong `libs/web-re-toolkit/crates/wre-template` nhằm phân tích cấu trúc DOM theo phương pháp vi phân (delta/diff-based) giữa $N \ge 2$ trang cùng layout/template:
- Loại bỏ toàn bộ boilerplate tĩnh (`<nav>`, `<footer>`, `<aside>`, banner, CSS classes, tracking scripts).
- Bóc tách nội dung động cốt lõi và xuất định dạng **Skeleton + Slot** trực quan cho LLM, giảm 70–90% token tiêu thụ.
- Xử lý triệt để 3 bẫy ngoại lệ:
  1. Bảo toàn ngữ cảnh nhãn tĩnh khi đi liền giá trị động (Label-sibling context: `<span>Tác giả:</span> <span>Nguyễn Văn A</span>`).
  2. Semantic whitelist không bao giờ prune (`h1`–`h6`, `time`, đoạn văn bản dài $\ge 80$ ký tự) để chống trùng lặp ngẫu nhiên.
  3. Khử boilerplate nhiễu theo request (timestamp, view counter) bằng cơ chế Dual-Hash (`hash_raw` vs `hash_norm`).
- Hỗ trợ container danh sách động (`StructuralDynamic`) và tích hợp lệnh CLI `wre template diff`.

---

## 2. Đã làm được gì (Chi tiết thay đổi)

1. **Khởi tạo và tích hợp Crate vào Workspace:**
   - Crate mới [`wre-template`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template) với `edition = "2024"`.
   - Đăng ký vào workspace tại [`libs/web-re-toolkit/Cargo.toml`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/Cargo.toml).
   - Tích hợp dependency: `twox-hash = "2.1.3"` (xxHash64), `scraper = "0.29.0"`, `ego-tree = "0.11.1"`, `regex`, `serde`, `serde_json`, `thiserror`.

2. **Kiến trúc module tuân thủ tuyệt đối Single Responsibility (Một file - Một logic duy nhất):**
   - [`dom_tree.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/dom_tree.rs): Parse HTML thô thành `CleanDomTree` gọn nhẹ, loại bỏ `<script>`, `<style>`, `<noscript>`, `<iframe>`, `<svg>`, `<template>` và HTML comments; chỉ giữ các thuộc tính ngữ nghĩa whitelist (`href`, `src`, `datetime`, `content`, `alt`, `title`); phân loại semantic leaf (`h1`-`h6`, `time`, text $\ge 80$ ký tự) và semantic container (`article`, `main`).
   - [`hasher.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/hasher.rs): Hash cây bottom-up độ phức tạp $O(N)$ bằng `XxHash64`. Sinh `DualHash`:
     - `hash_raw`: băm tag, own text thô, whitelist attributes, và sorted children hashes.
     - `hash_norm`: băm với text đã thế regex placeholders cho ngày ISO/RFC, số/counter, UUID, token hex.
   - [`path.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/path.rs): Tính toán đường dẫn cấu trúc XPath chuẩn (`CanonicalPath`, ví dụ `body[1]/main[1]/article[1]/h1[1]`) và hỗ trợ wildcard pattern cho dynamic list (`li[*]`).
   - [`classifier.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/classifier.rs): Tập hợp thống kê path qua $N$ trang mẫu và phân loại 6 trạng thái: `Stable`, `NoisyBoilerplate`, `DynamicLeaf`, `DynamicContainer`, `StructuralDynamic`, `Optional`.
   - [`pruner.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/pruner.rs): Lan truyền động bottom-up và bảo vệ 3 ngoại lệ:
     - Giữ nhãn tĩnh liền kề giá trị động (`can_be_label_context` chỉ áp dụng cho inline label descriptor $\le 60$ ký tự, ngăn chặn layout block như `aside`, `footer` biến thành nhãn).
     - Semantic whitelist bảo vệ `is_semantic_leaf()`.
     - Prune triệt để các node chỉ dynamic ở `hash_raw` nhưng stable ở `hash_norm` (`NoisyBoilerplate`).
   - [`skeleton.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/skeleton.rs): Serializer định dạng Skeleton phân cấp cho LLM, gom nhóm danh sách lặp (`[li] × 8`), hiển thị nhãn `← [label]`, `← [dynamic]`, tuỳ chọn chú thích XPath (`(xpath: ...)`), và hàm `extract_slots()` xuất mảng JSON slot có cấu trúc.
   - [`error.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/error.rs): Định nghĩa enum `TemplateError` với ngữ cảnh rõ ràng.
   - [`lib.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/lib.rs): Façade API `TemplateDiffPipeline` và `TemplateAnalysisResult`.

3. **Tích hợp CLI Subcommand:**
   - Tạo [`template_cmd.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-cli/src/template_cmd.rs) trong `wre-cli`.
   - Lệnh `wre template diff <page1.html> <page2.html> ...` hỗ trợ cờ `--xpath`, `--slots`, `--json`.
   - Build release binary thành công tại `libs/web-re-toolkit/target/release/wre`.

---

## 3. Làm tại đâu (Danh sách file & vị trí)

| File | Vị trí | Trách nhiệm |
|---|---|---|
| [`Cargo.toml`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/Cargo.toml) | `[workspace.dependencies]` | Đăng ký crate `wre-template` |
| [`crates/wre-template/Cargo.toml`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/Cargo.toml) | Toàn bộ file | Cấu hình dependencies: `scraper`, `ego-tree`, `twox-hash`, `regex`, `serde`, `thiserror` |
| [`crates/wre-template/README.md`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/README.md) | Toàn bộ file | Tài liệu kiến trúc, tính năng và ví dụ sử dụng |
| [`crates/wre-template/src/dom_tree.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/dom_tree.rs) | Toàn bộ file | Parse HTML, làm sạch thẻ rác, lọc whitelist thuộc tính |
| [`crates/wre-template/src/hasher.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/hasher.rs) | Toàn bộ file | Subtree bottom-up dual-hash (`raw` & `norm`) |
| [`crates/wre-template/src/path.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/path.rs) | Toàn bộ file | Tính toán canonical XPath phân cấp |
| [`crates/wre-template/src/classifier.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/classifier.rs) | Toàn bộ file | Phân loại trạng thái node qua đa trang |
| [`crates/wre-template/src/pruner.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/pruner.rs) | Toàn bộ file | Cắt tỉa cây DOM, bảo vệ label-sibling và semantic whitelist |
| [`crates/wre-template/src/skeleton.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/skeleton.rs) | Toàn bộ file | Render Skeleton và trích xuất slots cho LLM |
| [`crates/wre-template/src/error.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/error.rs) | Toàn bộ file | Định nghĩa `TemplateError` |
| [`crates/wre-template/src/lib.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/src/lib.rs) | Toàn bộ file | Public façade API `TemplateDiffPipeline` |
| [`crates/wre-template/tests/integration.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-template/tests/integration.rs) | Toàn bộ file | Test tích hợp bóc tách e-commerce và khử timestamp boilerplate |
| [`crates/wre-cli/Cargo.toml`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-cli/Cargo.toml) | `[dependencies]` | Thêm `wre-template.workspace = true` |
| [`crates/wre-cli/src/args.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-cli/src/args.rs) | `TemplateCommand`, `Command::Template` | Khai báo CLI flags cho lệnh `wre template diff` |
| [`crates/wre-cli/src/template_cmd.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-cli/src/template_cmd.rs) | Toàn bộ file | Điều phối đọc file HTML, phân tích template và xuất kết quả |
| [`crates/wre-cli/src/main.rs`](file:///data/projects/web-apps/aio_reverse/libs/web-re-toolkit/crates/wre-cli/src/main.rs) | `mod template_cmd`, match arm | Đăng ký và dispatch lệnh `Template` |

---

## 4. Hướng dẫn và kết quả Verify

### 4.1. Unit tests và Integration tests trong `wre-template`
Lệnh chạy:
```bash
cargo test -p wre-template
```
Kết quả thực tế:
```text
running 8 tests
test classifier::tests::classifies_stable_and_dynamic_nodes ... ok
test path::tests::builds_hierarchical_paths ... ok
test pruner::tests::preserves_label_sibling_for_dynamic_value ... ok
test skeleton::tests::renders_compact_skeleton ... ok
test dom_tree::tests::parses_simple_html_and_strips_script ... ok
test hasher::tests::normalizes_dates_and_numbers ... ok
test hasher::tests::dual_hash_detects_noisy_boilerplate ... ok
test tests::end_to_end_pipeline_extracts_article_and_prunes_nav ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/integration.rs
running 2 tests
test prunes_noisy_request_timestamp_boilerplate ... ok
test handles_dynamic_product_list_container ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
```

### 4.2. Clippy Linter Check
Lệnh chạy:
```bash
cargo clippy -p wre-template
```
Kết quả thực tế:
`Finished dev profile [optimized + debuginfo] target(s) in 0.13s` — 0 warning, 0 error trong `wre-template`.

### 4.3. Kiểm thử CLI end-to-end (`wre template diff`)
Lệnh chạy:
```bash
wre template diff /tmp/wre_template_test/page1.html /tmp/wre_template_test/page2.html
```
Kết quả thực tế:
```text
[document]
  [html]
    [body]
      [main]
        [h1] "Giá cổ phiếu công nghệ tăng vọt"  ← [dynamic]
        [div]
          [span] "Tác giả:"  ← [label]
          [span] "Trần Hoàng Nam"  ← [dynamic]
          [time] "2026-10-25"  ← [dynamic]
        [div]
          [p] "Các mã cổ phiếu ngành chip dẫn dắt đà tăng trưởng của thị trường."  ← [dynamic]

--------------------------------------------------
Analyzed 2 pages. Token / text reduction: 14.1%
```
*(Thanh `<nav>` và `<footer>` tĩnh đã bị loại bỏ 100%, cặp nhãn "Tác giả:" đi cùng tên tác giả được giữ nguyên vẹn).*
