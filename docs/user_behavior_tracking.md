# Dùng PostHog để thu thập và đưa dữ liệu hành vi về database

> Bản thử nghiệm hiện tại bỏ tag sản phẩm gán sẵn và persona user, dùng dữ liệu mới theo [hướng dẫn khởi động](startup.md). Không import lại lịch sử PostHog cũ nếu muốn thử nghiệm sạch; chọn project test mới hoặc giới hạn `--since` đúng thời điểm bắt đầu. Bỏ nhãn không tự loại bỏ ảnh hưởng của hành vi cũ.

Tài liệu này tập trung vào luồng PostHog: cấu hình project và credentials, gửi event vào PostHog, export event từ PostHog về NUTEE, lưu dữ liệu, chạy pipeline và kiểm tra lỗi. Đây là hướng dẫn theo kiến trúc/code hiện có trong dự án; không phải hướng dẫn chung về thiết kế recommendation.

## 1. Luồng dữ liệu tổng quan

```text
Trình duyệt / ứng dụng
    │  PostHog JS SDK: event + properties
    ▼
PostHog project
    │  HogQL Query API: đọc event đã được PostHog ingest
    ▼
pipeline.extract.export_posthog
    ├─ Bronze Parquet: bản raw để replay/audit pipeline
    └─ SQLite app.sqlite3 / posthog_events: bản export tra cứu, deduplicate
             │
             ▼
pipeline.run_pipeline --source bronze
    ├─ normalize, validate, deduplicate, sessionize
    ├─ Silver: events.parquet và rejected.parquet
    └─ Gold: user-product interaction, preferences, session sequences
```

**Quan trọng:** Gửi event từ trình duyệt lên PostHog không tự động ghi event đó vào SQLite của NUTEE. Cần có exporter chạy riêng để đọc dữ liệu từ PostHog, ghi bền vững vào Bronze và SQLite, rồi pipeline mới biến raw event thành Silver/Gold. Trong code hiện tại, event export được lưu ở bảng `posthog_events`, không tự động chèn vào bảng local `events`.

## 2. Các điều kiện cần chuẩn bị trên PostHog

1. **Tạo project riêng cho dữ liệu cần thu thập.** Dự án hỗ trợ tách project synthetic và real. Không dùng project test để chứa dữ liệu người dùng thật.
2. **Chọn đúng region/host** của project. Ví dụ US dùng ingestion host `https://us.i.posthog.com`, API host `https://us.posthog.com`; EU dùng các host EU tương ứng. Ingestion host và API host có thể khác nhau.
3. **Lấy Project API key** của project. Key này dùng để gửi event từ client/PostHog SDK hoặc simulator; frontend hiện đọc qua biến `VITE_POSTHOG_KEY`.
4. **Tạo Personal API key** có quyền truy vấn dữ liệu project. Exporter backend dùng key này để gọi Query API; đây là secret, không đưa vào frontend hoặc biến `VITE_*`.
5. **Lấy Project ID** của project. Exporter đưa ID vào đường dẫn Query API.
6. **Đảm bảo project giữ event đủ lâu** để exporter kịp chạy. Exporter có replay/lookback window và checkpoint; nếu event đã bị xóa/hết retention trước khi export, database đích không thể khôi phục event đó qua exporter này.
7. **Kiểm tra quyền truy cập API** cho Personal API key và khả năng chạy HogQL Query API trên project. Project ID, API key và host phải cùng region/project.

Trong NUTEE, exporter truy vấn event có `properties.app = 'nutee'` và `properties.synthetic` phù hợp với origin. Vì vậy, event cần mang các properties này và exporter chỉ import đúng namespace đã chọn.

## 3. Credentials và cấu hình môi trường

Thêm biến tương ứng vào `.env` ở thư mục gốc, không commit file chứa secret:

```dotenv
# Trình duyệt: gửi event vào PostHog test project
VITE_POSTHOG_KEY=phc_project_api_key
VITE_POSTHOG_HOST=https://us.i.posthog.com
VITE_POSTHOG_TEST_PROJECT=true

# Backend exporter và simulator: synthetic/test project
POSTHOG_TEST_PROJECT=true
POSTHOG_PROJECT_KEY=phc_project_api_key
POSTHOG_HOST=https://us.i.posthog.com
POSTHOG_API_HOST=https://us.posthog.com
POSTHOG_PROJECT_ID=12345
POSTHOG_PERSONAL_API_KEY=phx_private_personal_api_key

# Chỉ cấu hình riêng khi export origin real
POSTHOG_REAL_API_HOST=https://us.posthog.com
POSTHOG_REAL_PROJECT_ID=67890
POSTHOG_REAL_PERSONAL_API_KEY=phx_private_real_project_key
```

| Biến | Nơi sử dụng | Mục đích và lưu ý |
|---|---|---|
| `VITE_POSTHOG_KEY` | Frontend | Project API key để SDK gửi event. Vite biến có prefix `VITE_` được đóng gói vào browser, nên không được đặt Personal API key ở đây. |
| `VITE_POSTHOG_HOST` | Frontend | Ingestion host/region của project. |
| `VITE_POSTHOG_TEST_PROJECT` | Frontend | Phải là `true` để code hiện tại bật PostHog. Cờ này xác nhận đây là cấu hình test; frontend code hiện luôn gắn `synthetic=true`. |
| `POSTHOG_TEST_PROJECT` | Backend | Guard bắt buộc cho exporter/simulator synthetic, tránh gửi/import nhầm project ngoài ý muốn. |
| `POSTHOG_PROJECT_KEY` | Backend simulator | Project API key phục vụ lệnh gửi simulator; không phải key truy vấn exporter. |
| `POSTHOG_HOST` | Backend simulator | Ingestion host cho batch API của simulator. |
| `POSTHOG_API_HOST` | Backend exporter | API host sử dụng để gọi Query API. |
| `POSTHOG_PROJECT_ID` | Backend exporter | Project ID dùng trong `/api/projects/{project_id}/query/`. |
| `POSTHOG_PERSONAL_API_KEY` | Backend exporter | Secret xác thực truy vấn/export. Chỉ backend/máy chạy job được giữ key này. |
| `POSTHOG_REAL_*` | Backend exporter | Credentials riêng cho project real. Exporter từ chối nếu real project ID trùng `POSTHOG_PROJECT_ID`. |

Host mặc định trong code không đồng nhất hoàn toàn giữa các hàm; nên khai báo rõ host ingestion và API host thay vì phụ thuộc default. Sau khi đổi biến `VITE_*`, cần build/recreate frontend. Sau khi đổi biến backend, cần recreate backend/job runner. Không ghi key vào log, tài liệu chia sẻ, source control hoặc output debug.

Exporter backend xác thực Query API bằng header `Authorization: Bearer <PERSONAL_API_KEY>`. Nếu request không mang Personal API key hợp lệ, PostHog không trả dữ liệu để import; Project API key không thay thế được key truy vấn này.

## 4. Gửi event từ frontend lên PostHog

### Cách hoạt động hiện tại

Tracker nằm ở `frontend/src/services/posthog.js`:

1. `track(userId, eventName, properties)` tạo `event_id`, `timestamp`, `distinct_id`, `session_id`, `source`, `synthetic` và `environment`.
2. Frontend gửi event đến API NUTEE `/events`.
3. Chỉ khi local API xác nhận thành công, frontend gọi `posthog.capture(...)`.
4. `captureCloud()` gắn `$insert_id` bằng `event_id`, cùng `app: "nutee"` và metadata origin.

Do thứ tự trên, nếu `POST /events` lỗi thì frontend không gọi capture PostHog. Nếu PostHog chưa được bật, event local vẫn có thể được ghi nhưng không được gửi lên PostHog. Đây là behavior hiện tại của ứng dụng demo, không phải PostHog bắt buộc phải hoạt động theo cách này.

### Event và properties tối thiểu cho exporter

Exporter đọc các cột PostHog `uuid`, `timestamp`, `distinct_id`, `event`, `properties`, rồi tìm event bằng:

- `properties.app = 'nutee'`
- `properties.synthetic = true` cho origin `synthetic`, hoặc `false` cho origin `real`

Do đó, với một event muốn được exporter NUTEE lấy về:

- Event name phải được gửi đúng trong PostHog.
- Properties phải có `app: "nutee"`.
- Properties phải có `synthetic` Boolean đúng với project/luồng dữ liệu.
- Nên có `event_id` ổn định; exporter dùng `event_id`, sau đó `$insert_id`, sau cùng mới fallback về PostHog `uuid`.
- Cần có `distinct_id`, timestamp và properties theo event schema để pipeline xử lý.

Trong code frontend hiện tại, `captureCloud()` tự bổ sung `app`, `synthetic` và `$insert_id`. Nếu gửi trực tiếp bằng một SDK/producer khác, producer phải tự gửi các properties mà exporter đang lọc; nếu thiếu `app` hoặc gắn sai `synthetic`, event sẽ không được truy vấn/import.

### Xác nhận đã gửi thành công

Log `capture called (delivery not confirmed)` chỉ xác nhận SDK đã nhận lệnh capture. SDK có thể batch hoặc gửi bất đồng bộ; log đó **không chứng minh** PostHog đã ingest event. Phải kiểm tra event trên PostHog Events/Query hoặc export được event về database mới xác nhận đủ cả ingest và export.

## 5. Gửi event test bằng simulator (tùy chọn)

Mặc định simulator chỉ lưu event local. Chỉ gửi khi chủ động dùng dedicated synthetic/test project và đã cấu hình:

```dotenv
POSTHOG_TEST_PROJECT=true
POSTHOG_PROJECT_KEY=phc_project_api_key
POSTHOG_HOST=https://us.i.posthog.com
```

Lệnh gửi simulator:

```powershell
docker compose exec backend python -m data_generator.simulate_sessions --events 1000 --seed 42 --scenario S1_long_term --posthog
```

Lệnh này dùng batch API và project API key. Không dùng simulator để phát sinh dữ liệu giả vào project real. Startup ứng dụng không tự gửi simulator events lên PostHog.

## 6. Export event từ PostHog về SQLite và Bronze

### Lệnh export

Sau khi có event trong PostHog và đã cấu hình Project ID/Personal API key:

```powershell
docker compose exec backend python -m pipeline.extract.export_posthog --origin synthetic
```

Với project real đã cấu hình riêng:

```powershell
docker compose exec backend python -m pipeline.extract.export_posthog --origin real
```

Exporter hiện:

- Gọi HogQL Query API với keyset pagination theo `(timestamp, uuid)`.
- Chỉ đọc event có `app=nutee`, origin khớp và timestamp không muộn hơn thời điểm bắt đầu export.
- Mặc định dùng checkpoint của project và replay 48 giờ để nhận lại event đến trễ; `--lookback-hours` điều chỉnh cửa sổ này.
- Ghi raw events thành các file Parquet trong `data/{origin}/bronze/`.
- Ghi payload export vào bảng SQLite `posthog_events` với khóa `(origin, event_id)`; chạy lại không tạo bản ghi trùng.
- Chỉ cập nhật checkpoint sau khi ghi Bronze và SQLite thành công, giúp lần chạy sau có thể replay nếu job lỗi trước đó.
- Retry lỗi 429/5xx và lỗi kết nối theo backoff; lỗi cuối cùng vẫn được ném ra để job thể hiện thất bại.

Tham số hữu ích:

```powershell
# Mặc định page size 1000, replay 48 giờ
docker compose exec backend python -m pipeline.extract.export_posthog --origin synthetic

# Tăng/giảm page size và cửa sổ replay
docker compose exec backend python -m pipeline.extract.export_posthog --origin synthetic --page-size 500 --lookback-hours 72

# Backfill từ một thời điểm ISO có timezone
docker compose exec backend python -m pipeline.extract.export_posthog --origin synthetic --since 2026-10-01T00:00:00+00:00
```

Để exporter đưa dữ liệu về database một cách liên tục, cần lên lịch chạy lệnh export định kỳ bằng scheduler/orchestrator bên ngoài hoặc thiết lập scheduler phù hợp cho deployment. Repo hiện không tự chạy PostHog export theo lịch. Chạy một exporter writer cho mỗi origin tại một thời điểm; sau export có thể chạy pipeline tuần tự.

### Những nơi dữ liệu được lưu

| Lớp | Vị trí | Mục đích |
|---|---|---|
| Export database | `app.sqlite3`, bảng `posthog_events` | Payload event trả về từ PostHog, tra cứu theo origin và event ID. Không phải bảng local `events`. |
| Bronze | `data/synthetic/bronze/` hoặc `data/real/bronze/` | Raw envelopes đã export để replay và phục vụ pipeline. |
| Silver | `data/{origin}/silver/events.parquet` và `rejected.parquet` | Event đã chuẩn hóa/validate và các bản ghi bị từ chối. |
| Gold | `data/{origin}/gold/` | User-item scores, preferences, ALS interactions, session sequences. |

Trong Docker, các đường dẫn này nằm dưới data volume của backend (`/app/data`). Bảo đảm volume bền vững và được backup phù hợp; xóa volume sẽ xóa database, checkpoint và các lớp Parquet.

### Từ Bronze sang Silver/Gold

Sau khi export thành công, chạy:

```powershell
docker compose exec backend python -m pipeline.run_pipeline --source bronze --origin synthetic
```

Hoặc với real:

```powershell
docker compose exec backend python -m pipeline.run_pipeline --source bronze --origin real
```

Chạy export và pipeline là hai bước khác nhau. Export đưa PostHog events về Bronze/SQLite; pipeline làm sạch, đếm sự kiện và nhóm phiên. `--source bronze` có nghĩa là pipeline đọc Bronze đã tồn tại, không tự gọi PostHog API.

## 7. Theo dõi một event từ đầu đến cuối

1. Bật cấu hình PostHog test project và khởi động lại frontend/backend phù hợp.
2. Thực hiện một hành động trong ứng dụng, ví dụ mở sản phẩm.
3. Trong browser console, kiểm tra `event created`, sau đó `local database acknowledged` và `capture called`. Ghi lại `event_id`.
4. Trong PostHog project đúng region, tìm event theo event name và kiểm tra `properties.app`, `properties.synthetic`, `properties.event_id` hoặc `$insert_id`.
5. Chạy exporter `--origin synthetic`.
6. Xác nhận event được exporter ghi nhận (`posthog.event_imported` trong audit log/Data trace) và tồn tại trong `posthog_events`/Bronze.
7. Chạy pipeline `--source bronze`; kiểm tra event xuất hiện ở Silver hoặc có reason rõ ràng trong rejected.

Các audit stage liên quan có thể gồm `posthog.export_started`, `bronze.written`, `posthog.export_page_saved`, `posthog.event_imported`, `posthog.checkpoint_committed`, `posthog.export_completed`, `silver.validated`, `silver.rejected`, `gold.published`.

## 8. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra/khắc phục |
|---|---|---|
| PostHog không được khởi tạo trên frontend | Thiếu `VITE_POSTHOG_KEY` hoặc `VITE_POSTHOG_TEST_PROJECT` không phải `true` | Kiểm tra env frontend và rebuild/recreate frontend. |
| Có log local saved nhưng PostHog không có event | Cloud tracking tắt, local `/events` lỗi trước capture, sai ingestion host/key, hoặc SDK chưa gửi xong | Xem browser console/network; kiểm tra project key/host và Events trên đúng project. |
| Event có trên PostHog nhưng export trả 0 | Sai project ID/region, Personal API key/quyền truy vấn, sai `app`, sai Boolean `synthetic`, sai origin, thời gian ngoài cửa sổ | Kiểm tra properties trên event và truy vấn project tương ứng; backfill với `--since` nếu cần. |
| Export lỗi 401/403 | Personal API key không hợp lệ, thiếu quyền, key thuộc project/region khác | Tạo/kiểm tra key server-side và quyền truy cập Query API. |
| Export lỗi project/query | Project ID sai hoặc API host không khớp region | Đối chiếu project URL/region và `POSTHOG_*_API_HOST`. |
| Event vào Bronze nhưng không có ở Silver | Schema không hợp lệ, thiếu product/user, event name không hỗ trợ, sai origin/consent, future timestamp hoặc bot/dev noise | Kiểm tra `rejected.parquet` và audit reason; sửa producer/schema rồi export/replay phù hợp. |
| Event lặp lại giữa các lần export | Có thể là replay lookback có chủ đích | DB dùng khóa `(origin,event_id)` để deduplicate; Silver cũng deduplicate event ID. Kiểm tra ID ổn định để bảo đảm idempotency. |
| Checkpoint không tăng sau lỗi | Ghi Bronze/SQLite chưa hoàn tất hoặc job lỗi | Sửa lỗi storage/DB và chạy lại; exporter chỉ commit checkpoint sau khi dữ liệu được lưu. |

Không kết luận dựa riêng vào HTTP 200 của capture hoặc log client. Kiểm tra lần lượt PostHog ingest, export API result, durable Bronze/SQLite write và pipeline validation.

## 9. Dữ liệu thật, bảo mật và phân tách nguồn

- Frontend hiện tại phát `synthetic=true`, `environment=dev`; đây là tracker demo, không phải producer real.
- Với dữ liệu real, cần producer/luồng được thiết kế riêng, gửi `synthetic=false`, consent hợp lệ và origin/environment đúng. Không chỉ đổi biến môi trường để biến demo thành tracking production.
- Dùng PostHog project riêng cho real. Exporter yêu cầu credentials `POSTHOG_REAL_*` và chặn real project ID trùng synthetic project ID.
- Personal API key chỉ đặt ở backend secret store/environment; Project API key có thể xuất hiện phía client nhưng vẫn phải giới hạn đúng project.
- Chỉ thu thập properties cần thiết. Không gửi PII, credentials, thông tin thanh toán hoặc search query nhạy cảm. Cờ `consent=true` trong event là metadata, không chứng minh consent đã được xin hợp lệ.
- Phân tách project/origin khi export, lưu và chạy pipeline; không gộp real và synthetic.
- Hạn chế quyền truy cập `app.sqlite3`, Bronze raw và logs; đặt retention, backup, xóa dữ liệu và quy trình xử lý yêu cầu người dùng theo chính sách sản phẩm.
- Audit hiện dùng allowlist field để tránh ghi payload/query/secret ra log. Không thêm log dump toàn bộ request hoặc PostHog properties.

## 10. Checklist trước khi bật luồng PostHog → database

- [ ] Có PostHog project đúng region, dùng project test riêng cho synthetic.
- [ ] Frontend có đúng Project API key và ingestion host; `VITE_POSTHOG_TEST_PROJECT=true` khi dùng project test.
- [ ] Backend có đúng API host, project ID và Personal API key có quyền truy vấn.
- [ ] Personal API key không nằm trong `VITE_*`, source control hoặc log.
- [ ] Event có `app=nutee`, `synthetic` đúng kiểu Boolean/origin, event name và timestamp hợp lệ.
- [ ] `event_id` ổn định và được giữ trong PostHog để deduplicate/reconcile.
- [ ] Đã xác nhận event thực sự xuất hiện trên PostHog, không chỉ thấy `capture called`.
- [ ] Đã chạy exporter và xác nhận dữ liệu được ghi ở cả SQLite `posthog_events` lẫn Bronze.
- [ ] Đã chạy pipeline Bronze → Silver/Gold và kiểm tra rejected events.
- [ ] Có lịch chạy export định kỳ, giám sát lỗi/job duration/checkpoint và backup volume.
- [ ] Real tracking có consent, project/credentials tách biệt, dữ liệu được giảm thiểu và access/retention được quy định.
