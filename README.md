# NUTEE — Demo sản phẩm và dữ liệu hành vi

NUTEE cung cấp website mua sắm giả lập, sản phẩm có thông số kỹ thuật, tracking,
simulator và pipeline dữ liệu. Người cộng tác nhận catalog/lịch sử sạch để tự
xây dựng recommendation. **Toàn bộ implementation của hệ gợi ý đã được gỡ**:
không có model, scoring, train/evaluate, serving hoặc API placeholder. Thư mục
`recommendation/` chỉ giữ các file Python rỗng làm khung bàn giao.

## 1. Clone và chạy bằng Docker

Cần Docker Desktop/Engine chạy Linux containers, Compose v2, mạng để tải image/
dependency và port 8000/8080 chưa bị chiếm. Không cần Python, Node, DB server
hoặc tài khoản PostHog trên máy host.

Sau khi clone source và vào thư mục chứa `docker-compose.yml`, chọn một cách:

```sh
# Website + catalog/user; 0 event nếu volume hoàn toàn mới
docker compose up -d --build

# Hoặc: website + tạo 100.000 event và chạy pipeline
docker compose --profile demo up -d --build
```

Demo mặc định không cần `.env`. Có thể copy `.env.example` thành `.env` để cấu
hình PostHog/backend. Không commit credentials thật. Dữ liệu không đi theo clone:
Docker volume, `data/` và `runtime/` đều nằm ngoài source GitHub.

```sh
docker compose ps -a
docker compose --profile demo logs -f demo-data
```

Backend phải healthy. Job `demo-data` **Exited (0)** là thành công; chờ summary
cuối log, vì `up -d` không chờ tạo dữ liệu hoàn tất. Ctrl+C chỉ thoát xem log.
Không chạy nhiều job ghi pipeline trên cùng dataset đồng thời.

| Trang | Địa chỉ |
| --- | --- |
| Website / Shop all | http://localhost:8080 / http://localhost:8080/products |
| Data trace | http://localhost:8080/data-trace |
| Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

Lần đầu có thể mất vài phút tải/build. Đây là demo local, chưa phải production:
user picker không phải đăng nhập, checkout không thu tiền, chưa có consent UI.

## 2. Phạm vi và luồng dữ liệu

```text
Website → FastAPI → SQLite events
   └─ tùy chọn → PostHog → exporter → posthog_events + Bronze
Simulator → JSONL/Parquet + SQLite events
                              ↓
                   Bronze → Silver → Gold
                              ↓
              Dữ liệu bàn giao cho collaborator
```

| Phần | Đã có |
| --- | --- |
| Storefront | Trang chủ, danh sách/tìm kiếm, chi tiết, wishlist, giỏ, checkout demo |
| Product domain | 7 bảng normalized, thông số, SKU, JSON projection cho UI |
| Tracking | Validate, dedup, session, local trước; PostHog tùy chọn |
| Simulator | Lịch sử có seed, session funnel, manifest/hash |
| Pipeline | Chuẩn hóa, làm sạch, đếm sự kiện, nhóm phiên, quarantine |
| Tests/Docker | Chạy toàn bộ bằng containers, test DB riêng |
| Recommendation | Chỉ khung file rỗng; collaborator tự triển khai |

Pipeline **không** gán trọng số hành vi, tính recency/strength/confidence, xây
profile sở thích hay train model. Các quyết định đó thuộc phần việc recommendation.

## 3. Cấu trúc source và dịch vụ

```text
backend/                   FastAPI, schemas, SQLite, catalog repository, audit
data_generator/            User/product generators và session simulator
pipeline/                  Export PostHog, Bronze/Silver/Gold
scripts/start.py           Startup: seed catalog nếu thiếu, chuẩn bị pipeline
scripts/demo.py            Tạo lịch sử và validate/ETL; không train
configs/                   Event/product schema, simulator, pipeline config
frontend/                  React/Vite, tracking, Nginx
recommendation/            File structure rỗng cho collaborator
tests/                     Product, checkout, tracking, pipeline, PostHog tests
docs/                      Schema, startup, tracking, log demo
runtime/                   Bản xuất local; không commit
```

`frontend` service build với Node 22, Nginx phục vụ static và proxy `/api` tới
backend. `backend` dùng Python 3.13/FastAPI và SQLite trong volume
`nutee-product-demo-data` tại `/app/data`. Không có PostgreSQL container.
`demo-data` là one-shot job profile `demo`; `tests` là runner profile `test`,
network tắt, DB tạm, không truy cập volume ứng dụng. PostHog là dịch vụ ngoài,
không cần để chạy demo local. Dependencies ML đã bị gỡ khỏi image.

## 4. Product schema

| Bảng | Vai trò |
| --- | --- |
| `product` | ID số, code, tên, mô tả, rating, sold_count, published, timestamps |
| `product_variant` | SKU duy nhất, giá và tồn kho; FK tới product |
| `product_specification` | Tên/giá trị thông số; unique `(product_id, specification_name)` |
| `brand` / `product_brand` | Thương hiệu và junction N:M |
| `category` / `product_category` | Loại hàng, parent tùy chọn và junction N:M |

Đã bỏ promotion/product_image; UI dùng icon bằng code. Không có tag gán sẵn
`gaming`, `performance`, `office`… Category laptop/tai nghe vẫn giữ vì là loại
hàng. User chỉ có ID/tên trung tính, không có nghề nghiệp/persona.

Phân biệt ID:

- `product.id`: số nguyên cho quan hệ SQL.
- `product.code`: như `P0001`, dùng trong Event.product_id và URL.
- SKU: như `SKU-P0001`, nhận diện biến thể bán được.
- User: như `U0001`, tương ứng Event.distinct_id.

Giá là USD nguyên, không âm; rating nullable 0–5; timestamps UTC. Mẫu có một
SKU mặc định/sản phẩm. Schema hỗ trợ nhiều SKU nhưng UI/checkout chỉ mua một
đơn vị SKU mặc định mỗi sản phẩm. Không có payment thật.

`products.payload` là projection JSON cho UI/pipeline, không phải entity thứ
tám của ERD. `attributes` phản ánh specifications, price/stock phản ánh SKU mặc
định. Checkout cập nhật SKU, sold_count và projection cùng transaction. Không
sửa một bản riêng lẻ rồi để bản còn lại lệch. Seed lại không reset tồn kho.

Laptop có CPU/RAM/SSD/màn hình/pin; điện thoại có chipset/camera/pin; tai nghe có
ANC/driver/Bluetooth; màn hình có resolution/panel/refresh… Các thông số là dữ
liệu giả lập, không phải cấu hình thương mại được xác minh. Chuỗi specification
cần được parse đơn vị/kiểu nếu collaborator dùng làm features.

[Product schema](docs/product-schema.md) · [JSON Schema](configs/product_schema.json)
· [PostgreSQL DDL](docs/sql/product_schema.postgresql.sql). Runtime vẫn là SQLite;
DDL PostgreSQL chỉ là bản bàn giao, chưa triển khai hay kiểm tra trên server.

## 5. Tracking và dữ liệu giả lập

Các event hỗ trợ: `product_impression`, `product_click`, `product_view`,
`search`, `add_to_wishlist`, `add_to_cart`, `remove_from_cart`, `purchase`.

- UUID event_id chống lưu trùng; timestamp phải có timezone, normalize về UTC.
- distinct_id/session_id nhận diện người và phiên; frontend đổi session khi
  đổi user hoặc inactive >30 phút. ETL có fallback khi thiếu session.
- product_id bắt buộc trừ search; search cần query không rỗng.
- `page`, `list_id`, `position` là ngữ cảnh hiển thị, không phải metadata model.
- Impression ghi khi card hiện ít nhất 50%; mỗi lần mount/list có tracking riêng.
- Browser ghi local qua API trước, rồi mới gửi PostHog nếu bật. Local thành công
  không chứng minh PostHog đã ingest; không có transaction giữa hai hệ thống.
- `/events` không nhận purchase trực tiếp; `/checkout` tạo order/purchase server,
  chống đơn trùng và trừ tồn kho transactionally.
- Wishlist/cart UI lưu sessionStorage theo user, chưa phải server cart đầy đủ.
- Cả simulator và thao tác website demo đều `synthetic=true`. Real data cần
  producer có consent và storage/project riêng; không trộn hai nguồn.

Trên dataset sạch với seed 42: **1.000 users, 300 products, 300 SKUs, 1.860 specs,
100.000 events, 7.348 sessions**; xem [demo-log](docs/demo-log.json).

```sh
# Backend đã chạy; cách khác để tạo history ngoài profile demo
docker compose exec -T backend python -m scripts.demo --events 100000 --seed 42
```

Simulator chọn sở thích ngầm theo ID sản phẩm + seed, có exposure/click/view/
wishlist/cart/purchase, noise, ảnh hưởng vị trí và ngân sách phiên. Không dùng
nghề nghiệp/tag để tạo hành vi. S1 giữ tập ưa thích ổn định, S2 đổi tập về cuối
timeline, S3 dành nhóm user/item cold-start; cấu hình tại `configs/simulator.json`.
Timeline cố định theo config, không phải thời điểm chạy script. Mẫu hiện chưa
sinh search/remove_from_cart, nhưng website vẫn tracking được hai hành vi đó.

Cùng config/count/seed/catalog tạo cùng event IDs, DB bỏ qua trùng. Đổi catalog
hoặc tồn kho/seed/count có thể tạo history mới, không phải reset dataset.
Simulator purchase **không** tạo orders thực, không giảm kho/tăng sold_count;
chỉ là lịch sử hành vi. Các giả định mô phỏng vẫn tạo bias, không chứng minh
hiệu quả thực tế. Không dùng sở thích ngầm simulator làm ground truth model.

## 6. Pipeline và dữ liệu bàn giao

```sh
docker compose exec backend python -m pipeline.run_pipeline --source local --origin synthetic
```

Bronze giữ raw events. Source local append event SQLite chưa có trong Bronze rồi
đọc Bronze; source bronze chỉ đọc raw đã có, không tự gọi PostHog exporter.
Silver validate, UTC, dedup event ID/purchase, sessionize và ghi rejected IDs.
Gold chỉ là tổng hợp trung tính, không có scoring hoặc labels định sẵn:

```text
/app/data/
  app.sqlite3
  mock/users.json, products.json
  logs/audit.jsonl
  synthetic/
    raw/<scenario-seed-hash>/events.jsonl, events.parquet, manifest.json
    raw/demo-summary.json
    bronze/*.parquet
    silver/events.parquet, rejected.parquet
    gold/manifest.json
    gold/<generation>/user_item_event_counts.parquet
    gold/<generation>/session_sequences.parquet
  real/                              namespace riêng
```

`user_item_event_counts` gồm user_id, product_id, event_name, event_count,
first_timestamp, last_timestamp. Không cap số lần tương tác hay giảm trọng số
theo tuổi. `session_sequences` giữ thứ tự tất cả event đã clean, kể cả impression;
item_ids có thể null với search. Đọc manifest để lấy generation hiện hành.

Muốn nhận dữ liệu ra host:

```sh
docker compose cp backend:/app/data/mock ./exported-mock
docker compose cp backend:/app/data/synthetic ./exported-synthetic
```

Không copy SQLite đang chạy như một backup hoàn chỉnh vì có WAL; dùng SQLite
backup API hoặc dừng writer. Bản xuất local nằm ở `runtime/product-demo/`, không
đi theo GitHub. Raw history giữ nguyên qua đợt dọn source; Gold cần ETL lại để
chuyển sang counts/sequences mới.

## 7. API hiện hành

| Endpoint | Chức năng |
| --- | --- |
| `GET /health` | Liveness |
| `GET /users?limit=1000` | ID/tên trung tính; mặc định 100 users |
| `GET /products?q=&category=&offset=0&limit=24` | Danh sách/tìm theo tên, category, brand |
| `GET /products/P0001` | Projection có variants/specifications |
| `GET /catalog/products/P0001` | Product normalized và các quan hệ |
| `POST /events` | Validate/lưu tracking, không nhận purchase |
| `POST /checkout` | Order demo + cập nhật SKU + purchase event |
| `GET /analytics/status` | Counts và manifest pipeline |
| `GET /internal/events` | Trace local/imported events; không phải API tải hết dataset |
| `POST /internal/pipeline/run` | Chạy ETL |
| `GET /internal/metrics` | Counts, product_list_ctr mô tả hành vi |

Không còn `/recommendations/*`, `/internal/models/*` hay cờ AI_ENABLED. Các
đường dẫn đó trả 404. Data trace chỉ đọc event/pipeline. Internal API ngoài dev
cần `X-Internal-Token`; storefront hiện không có auth production.

## 8. Người làm recommendation nhận gì và làm gì?

Nhận catalog có specifications, Silver events và Gold counts/sequences.
`recommendation/` chỉ có `__init__.py`, `hybrid.py`, `ranking.py`, `scoring.py`,
`evaluation.py` **rỗng**. Tên file không bắt buộc thuật toán; có thể tổ chức lại.
Không có implementation cũ, dependency ML hoặc API để bật bằng biến môi trường.

**Mục tiêu bàn giao:** xây phần AI đề xuất sản phẩm và tích hợp kết quả vào danh
sách sản phẩm ngay trên trang chủ. Không tạo trang/tab “gợi ý cá nhân” riêng.
Hiện trang chủ chỉ hiển thị sản phẩm từ `/products`; toàn bộ việc tạo features,
train, đánh giá và phục vụ kết quả bên dưới đều chưa được triển khai.

### Đầu vào đã có và ranh giới trách nhiệm

- Phần dữ liệu/ứng dụng đã có: schema sản phẩm và thông số kỹ thuật, user ID/tên,
  tracking, checkout demo, simulator, ETL Bronze/Silver/Gold và Docker chạy app.
- Người phụ trách AI sử dụng các đầu vào này, tự xây toàn bộ module recommendation
  và phối hợp sửa backend/frontend để tích hợp. Không phải làm lại bộ sinh dữ liệu
  hay checkout. Nếu thiếu trường dữ liệu, thống nhất schema trước khi thay đổi.
- Dùng `product.code` (ví dụ `P0001`) làm ID liên kết với event, không nhầm với
  ID số của bảng product. User không có nghề nghiệp/persona; sản phẩm không có
  tag sở thích gaming/performance. Category, brand và thông số kỹ thuật vẫn có.
- Dataset mẫu là synthetic. Sở thích ngầm trong simulator không phải feature
  được phép lấy trực tiếp làm đầu vào hoặc nhãn đánh giá model.

### Công việc người phụ trách AI phải thực hiện

| Bước | Công việc cụ thể | Đầu ra cần bàn giao |
| --- | --- | --- |
| 1. Chốt bài toán | Ưu tiên top-N sản phẩm cho trang chủ theo user và lịch sử; xác định sự kiện mục tiêu, số lượng sản phẩm và khi nào cập nhật kết quả. Related-items/next-item là phần mở rộng nếu thống nhất thêm. | Mô tả mục tiêu, định nghĩa nhãn và tiêu chí đánh giá. |
| 2. Chuẩn bị dữ liệu | Đọc Silver; chuẩn hóa specifications/đơn vị, xử lý thiếu dữ liệu, ánh xạ user/item IDs. Tự chọn cách dùng click/view/cart/purchase, trọng số, giới hạn lặp, recency và negative sampling nếu cần. Không mặc định mọi sản phẩm chưa tương tác là không thích. | Code tạo dataset/features, ID mapping và cấu hình có thể tái lập. |
| 3. Chia tập | Chia train/validation/test theo thời gian, xử lý ranh giới session; chỉ xây features từ lịch sử có trước thời điểm dự đoán. Gold hiện có tổng hợp toàn tập nên phải tính lại theo từng cutoff nếu dùng để train/evaluate. | Split/cutoff rõ ràng, seed và kiểm tra tránh rò rỉ dữ liệu. |
| 4. Xây baseline và model | Làm baseline đơn giản trước, ví dụ popularity từ tập train; sau đó chọn content-based, collaborative hoặc hybrid và so sánh công bằng. Tên file `hybrid.py` không bắt buộc phải làm hybrid. | Code train, cấu hình và model có thể tái tạo bằng lệnh. |
| 5. Đánh giá | So sánh trên cùng split và tập candidate, công bố K; chọn chỉ số như Recall@K, NDCG@K, coverage phù hợp mục tiêu. Kiểm tra riêng user mới, item mới, lịch sử ít và sở thích thay đổi. | Báo cáo baseline/model, cách tính metrics, giới hạn dữ liệu synthetic và kết luận chọn model. |
| 6. Lưu và phục vụ model | Lưu/load model cùng ID mapping, phiên bản, cutoff, config/seed và metadata cần thiết. Tách train khỏi request; quy định lúc cập nhật model/cache và cách quay lại phiên bản trước. | Artifacts, lệnh train/load, xử lý model thiếu/hỏng/không tương thích. |
| 7. Xây API | Thống nhất request/response với backend: user ID, số lượng cần lấy, danh sách product code theo thứ tự và trạng thái fallback. Lọc sản phẩm chưa publish/hết kho, loại trùng; có fallback cho user mới và khi model lỗi/chưa có. | API được triển khai, tài liệu contract, test và giới hạn thời gian phản hồi đã đo. |
| 8. Tích hợp trang chủ | Phối hợp sửa `frontend/src/App.jsx` và `Home.jsx`; thống nhất cách trộn hoặc sắp xếp sản phẩm đề xuất trong danh sách chung. Giữ trang chủ hoạt động bằng danh sách sản phẩm thông thường khi AI không sẵn sàng. | Trang chủ dùng được kết quả AI, không thêm mục gợi ý riêng và không mất chức năng mua hàng. |
| 9. Kiểm thử và đóng gói | Bổ sung dependencies, tests và Docker cho phần AI; model lưu ở vị trí bền vững ngoài image nếu cần. Viết hướng dẫn lấy dữ liệu, train, evaluate, chạy serving và rebuild. | Người clone repo chạy lại được bằng các lệnh Docker đã ghi rõ. |

Khi nối UI, giữ tracking theo các shopping events hiện có: `product_id` là code,
`position` là vị trí thực sau khi trộn/sắp xếp, `list_id` ứng với danh sách đã render.
Không tự thêm event/field recommendation vào schema. Nếu cần đo attribution/A/B
thì thống nhất thay đổi contract riêng với người phụ trách dữ liệu. Tránh vòng
lặp impression → refresh danh sách → impression; không train trong mỗi request.

### Điều kiện hoàn thành phần AI

- Có lệnh Docker tái lập đầy đủ: tạo dữ liệu → chuẩn bị features/split → train →
  evaluate → khởi động serving; ghi rõ bước nào thủ công, bước nào tự động.
- Có báo cáo so sánh baseline/model trên cùng điều kiện, cấu hình và phiên bản
  artifacts; không dùng CTR/số liệu synthetic để khẳng định hiệu quả người dùng thật.
- Có test user/item mới, lịch sử trống, item hết kho/chưa publish, loại trùng,
  model thiếu/lỗi, và tính nhất quán ID giữa API, sản phẩm, events.
- Trang chủ nhận kết quả AI; khi không có model hoặc serving lỗi vẫn duyệt sản
  phẩm và checkout được. Có hướng dẫn fallback/rollback và tài liệu API mới.

Các mục trên là **công việc tương lai của người phụ trách AI**, không phải tính
năng đã tồn tại trong bản demo hiện tại.

## 9. Build, test, GitHub và giới hạn

```sh
docker compose up -d --build
docker compose --profile test run --rm --no-deps --build tests
docker compose --profile demo down
```

`restart` không build source mới. Rebuild/down giữ volume; `down -v` xóa volume.
Chỉ cần `build --no-cache` khi thực sự muốn bỏ cache. Frontend VITE variables
được lấy lúc build, thay đổi cần rebuild. Docker và local không chung data dir.
Test runner mount tests read-only, dùng DB tạm, network tắt.

Commit source, lockfile frontend, requirements, Docker/Compose, configs, tests,
`.env.example`, docs. Không commit `.env`, credentials, venv/node_modules/dist,
SQLite, raw data, artifacts, runtime. `.gitignore` không xóa secret đã commit.
Chủ dự án cần tạo Git repository/remote và publish; workspace chưa được push
lên GitHub trong quá trình hỗ trợ này. Người cộng tác fork/clone rồi chạy các
lệnh trên; không cần nhận volume riêng từ máy tác giả.

Giới hạn: SQLite/JSON demo, chưa PostgreSQL runtime; chưa auth/payment/consent UI
production, scheduler/distributed writers hoặc visual E2E đầy đủ. Python deps
và base images chưa pin tuyệt đối, không bảo đảm build byte-identical theo thời
gian. Simulator không đại diện real traffic. Không có CI tự động hiện tại.

| Lỗi thường gặp | Xử lý |
| --- | --- |
| Docker daemon/pipe unavailable | Mở Docker Desktop, Linux containers, kiểm tra `docker info` |
| Port 8000/8080 bận | Dừng app khác hoặc đổi host ports |
| Không có 100k events | Chờ demo-data Exited (0) hoặc chạy scripts.demo |
| Thay code không thấy đổi | Build/recreate, Ctrl+F5, không chỉ restart |
| Data local khác container | Kiểm tra NUTEE_DATA_DIR và volume |
| PostHog trống | Local và ingestion/export là các bước riêng; kiểm tra cấu hình và network |

Tài liệu còn lại: [startup](docs/startup.md), [product schema](docs/product-schema.md),
[event schema](docs/event-schema.md), [PostHog](docs/user_behavior_tracking.md),
[demo log](docs/demo-log.json), [verification](VERIFICATION.md).
