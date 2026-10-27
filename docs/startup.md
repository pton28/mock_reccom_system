# Chạy demo và build lại

Tại thư mục gốc có `docker-compose.yml`, bật Docker Desktop/Linux containers.
Không cần `.env` cho mặc định; cấu hình tùy chọn dùng `.env.example`.

```sh
# Chỉ app và catalog, không tự sinh lịch sử
docker compose up -d --build
# Hoặc app + job tạo 100.000 sự kiện
docker compose --profile demo up -d --build
docker compose --profile demo logs -f demo-data
```

Chờ backend healthy và demo-data Exited (0) nếu chọn profile demo. Website
http://localhost:8080, Data trace `/data-trace`, Swagger http://localhost:8000/docs.
Repo không chứa dữ liệu volume. Không có recommendation implementation/API/cờ
bật model; thư mục `recommendation` chỉ là khung file rỗng.

## Build sau khi sửa code

```sh
docker compose build backend frontend
docker compose up -d --no-build
# Hoặc chỉ frontend khi backend đang chạy
docker compose build frontend
docker compose up -d --no-deps frontend
# Chỉ backend
docker compose build backend
docker compose up -d --no-deps backend
# Bỏ cache khi cần
docker compose build --no-cache
docker compose up -d --force-recreate --no-build
```

`restart` không cập nhật image/env mới. Rebuild không reset data. Đổi VITE_* cần
build frontend; tải lại trình duyệt bằng Ctrl+F5.

## Tạo lịch sử, làm sạch và test

```sh
docker compose exec -T backend python -m scripts.demo --events 100000 --seed 42
docker compose exec backend python -m pipeline.run_pipeline --source local --origin synthetic
docker compose --profile test run --rm --no-deps --build tests
```

Demo sinh JSONL/Parquet/SQLite và ETL, không gửi batch PostHog. Cùng seed/input
chống trùng ID; đổi catalog/tồn kho/seed/count có thể cộng thêm dữ liệu. Purchase
giả lập không tạo orders hoặc trừ kho. Gold hiện chỉ có event counts và session
sequences; không có trọng số, recency, confidence hay profile.

Dataset hiện nằm trong volume `nutee-product-demo-data`, mount `/app/data`.
Dữ liệu cũ giữ nguyên. Sau cập nhật source, chạy lại ETL để publish Gold mới.
Nếu dùng dữ liệu import PostHog, chọn `--source bronze` theo tài liệu tracking.
Không chạy nhiều writer pipeline cùng lúc.

## Local Windows nếu không dùng Docker

Terminal 1 tại gốc, cần Python 3.13:

```powershell
if (-not (Test-Path .venv\Scripts\python.exe)) { py -3.13 -m venv .venv }
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
$env:NUTEE_DATA_DIR = 'data/product-demo-v1'
$env:APP_ENV = 'dev'
.\.venv\Scripts\python.exe -m scripts.demo --events 100000 --seed 42
.\.venv\Scripts\python.exe -m scripts.start
```

Terminal 2, Node 22: `cd frontend`, `npm.cmd ci`,
`npm.cmd run dev -- --port 5173 --strictPort`. Mở http://localhost:5173.
Không chạy backend Docker và local cùng port 8000. Bỏ lệnh scripts.demo nếu chỉ
muốn ghi nhận hành vi thủ công. Môi trường host không dùng cùng DB Docker.

## Dừng

```sh
docker compose --profile demo down
```

Không thêm `-v` nếu muốn giữ volume. Local dừng Ctrl+C. Bản xuất để bàn giao nằm
ở `runtime/product-demo/` trên máy tác giả và không được commit; người clone có
thể tạo lại bằng profile demo. Xem [README](../README.md) để hiểu schema và việc
của collaborator, [VERIFICATION](../VERIFICATION.md) để xem kiểm tra mới nhất.
