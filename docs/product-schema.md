# Product domain — bản demo đã triển khai

Thiết kế sản phẩm bỏ hoàn toàn
`promotion`, `product_image` và `product.promotion_id`; không chuyển các trường
khuyến mãi/ảnh sang bảng khác. Icon giao diện là minh họa bằng code, không phải
entity ảnh. Event schema được giữ nguyên.

## 7 bảng

| Bảng | Nội dung |
| --- | --- |
| product | ID số, code tương thích event, tên, mô tả, rating, số đã bán, trạng thái xuất bản, timestamps |
| product_variant | SKU duy nhất tối đa 16 ký tự, giá, số lượng, product FK |
| product_specification | Cặp tên/giá trị thông số theo sản phẩm; duy nhất `(product_id, specification_name)` |
| brand | Danh sách thương hiệu |
| product_brand | Quan hệ N:M sản phẩm/thương hiệu |
| category | Loại sản phẩm, `parent` tùy chọn trỏ về category |
| product_category | Quan hệ N:M sản phẩm/loại hàng |

Ứng dụng dùng SQLite: [migration runtime](../backend/catalog.sql), tự áp dụng
khi `init_db()`. [DDL PostgreSQL](sql/product_schema.postgresql.sql) có cùng
quan hệ, dùng SERIAL và TIMESTAMPTZ; đây là artifact bàn giao, chưa chuyển
runtime sang PostgreSQL hoặc xác minh trên server PostgreSQL.

## Quyết định cho demo

- `avg_rating` sửa từ NUMERIC(1,1) thành NUMERIC(2,1), CHECK 0–5. Chưa có review
  nên để NULL; không bịa rating từ lượt nhấp.
- Giá là số nguyên USD theo storefront hiện có; giá/tồn kho không âm. Không có
  giá giảm, promotion hay image URL. Thiết kế chưa hỗ trợ tiền tệ khác.
- Timestamp được ứng dụng ghi UTC; quan hệ FK không cascade delete.
- `product.code` giữ ID như P0001 cho event và URL; `product.id` là ID số cho FK.
- Mỗi sản phẩm demo có một SKU mặc định. Bảng/schema hỗ trợ nhiều SKU, nhưng
  checkout hiện chỉ mua một đơn vị SKU mặc định cho mỗi sản phẩm.
- SQLite `products.payload` là projection tương thích storefront/pipeline cũ,
  không phải entity thứ tám của ERD. `price`/`stock` phản ánh SKU mặc định;
  `attributes` phản ánh thông số. Checkout cập nhật projection, SKU và sold_count
  cùng transaction. Seed lại không reset tồn kho.
- Một thương hiệu/category được seed cho mỗi sản phẩm; junction cho phép N:M.
- Không có tag sở thích hoặc persona/nghề nghiệp user.

## Thông số

Laptop: CPU, RAM, SSD, màn hình, pin. Điện thoại/tablet: RAM, lưu trữ, màn hình,
pin, camera/chipset khi phù hợp. Tai nghe: driver, ANC, pin, Bluetooth. Bàn phím:
switch, số phím, kết nối. Chuột: DPI, trọng lượng, nút, kết nối. Màn hình: độ
phân giải, refresh rate, panel. Camera: sensor, megapixel, video, lens mount.
Loa: công suất, pin, chống nước. Wearable: màn hình, pin, GPS, chống nước.

Các thông số được tạo giả lập để demo, không phải cấu hình sản phẩm thương mại
đã xác minh. Trong bảng specification, đơn vị nằm trong tên (`ram_gb`,
`battery_mah`...) hoặc chuỗi giá trị; không thêm entity attribute riêng.

## API và bàn giao

- `GET /products`: danh sách projection để duyệt/tìm sản phẩm.
- `GET /products/P0001`: projection có variants/specifications, được kiểm tra
  bởi Pydantic `Product` trong [schemas.py](../backend/schemas.py).
- `GET /catalog/products/P0001`: dữ liệu normalized gồm product, variants,
  specifications, brands, categories và ID số.
- [JSON Schema](../configs/product_schema.json) được xuất từ Pydantic.
- Recommendation contains empty files only; no AI implementation or API remains.
- Chạy [hướng dẫn demo](startup.md); lịch sử có JSONL/Parquet, SQLite và summary.
