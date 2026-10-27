# Xác minh bản sản phẩm và tracking

Đợt dọn source 2026-10-27:

- Xóa implementation train/evaluate/ranking/scoring và cấu hình/dependency ML.
- `recommendation/*.py` chỉ là file rỗng, ứng dụng không import.
- Xóa API/cờ bật model và UI diagnostics model; pipeline chỉ clean/count/session.
- Giữ product schema, checkout, tracking, simulator, PostHog và dữ liệu bàn giao.
- Xóa roadmap/archive/model reports và bản sao kiểm thử sinh ra không còn cần.

Kết quả xác minh ngày 2026-10-27 trên source sau dọn:

- `docker compose --profile test run --rm --no-deps --build tests`: **30 passed** (5,73 giây). Một cảnh báo deprecation từ Starlette TestClient/httpx; không có test lỗi.
- `docker compose build backend frontend`: thành công; `docker compose up -d --no-build`: backend healthy, frontend chạy.
- HTTP 200: `/health`, `/products`, `/catalog/products/P0001`, `/openapi.json` và trang frontend. OpenAPI không còn route recommendation/model; URL recommendation và model status cũ trả 404.
- Image backend không còn implicit, faiss, sklearn, fastembed. Toàn bộ năm file Python trong `recommendation/` có kích thước 0 byte.
- Pipeline xử lý **100.000 events**, **1.000 users**, **7.348 sessions**, không có event bị loại; Gold hiện tại chỉ gồm `user_item_event_counts` (90.559 dòng) và `session_sequences` (7.348 dòng).
- SQLite giữ đủ 100.000 events; kiểm tra foreign key không có lỗi. Hai bảng model cũ được xác nhận rỗng trước khi xóa khỏi database demo; bản backup được cập nhật tại `runtime/product-demo/app.sqlite3`.
- Kiểm tra cú pháp Python và liên kết Markdown nội bộ thành công. Đã dọn cache Python và frontend build cũ trong workspace.

Dữ liệu gốc và các volume lịch sử được giữ nguyên. Các thế hệ Gold cũ trong volume là dữ liệu dẫn xuất lịch sử; pipeline hiện tại chỉ đọc manifest mới. Không có kiểm thử chất lượng model vì phần đó đã được gỡ. PostgreSQL chỉ có DDL bàn giao, runtime vẫn dùng SQLite. Kiểm tra frontend ở đây gồm build và HTTP smoke, chưa phải kiểm thử tương tác bằng trình duyệt.
