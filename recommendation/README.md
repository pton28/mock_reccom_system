# Huấn luyện ALS và khung tích hợp

Đã bổ sung quy trình ALS offline trong `scripts/`. Chạy từ thư mục gốc repo:

```powershell
.\.venv\Scripts\python.exe -m pip install -r recommendation/requirements.txt
.\.venv\Scripts\python.exe -m scripts.build_interaction_matrix
.\.venv\Scripts\python.exe -m scripts.train_als
.\.venv\Scripts\python.exe -m scripts.evaluate_als
.\.venv\Scripts\python.exe -m scripts.tune_als
.\.venv\Scripts\python.exe -m scripts.check_als_seeds
# Đánh giá lại mô hình đã tối ưu:
.\.venv\Scripts\python.exe -m scripts.evaluate_als --tuned
# Chốt mô hình và đánh giá test (từ chối ghi đè kết quả test đã có):
.\.venv\Scripts\python.exe -m scripts.evaluate_final
```

Đầu vào: `data/processed/train.csv` từ `scripts.prepare_mock_data`.
Ma trận và ánh xạ ID: `outputs/matrices/`. Mô hình, ánh xạ ID và cấu hình:
`outputs/models/als.npz`, `als_ids.npz`, `als_config.json`.
ALS học mới trên dữ liệu mock. `train_als` lưu cấu hình khởi đầu;
`tune_als` thử 48 tổ hợp factors (16/32/64/128), regularization (0.01/0.1/1),
alpha (1/5/20/50), giữ 20 iterations. Sau đó thử 40 và 80 iterations
cho tổ hợp tốt nhất. Chọn theo NDCG@10 validation, giữ seed 42.
`check_als_seeds` so sánh cấu hình ban đầu và cấu hình đã chọn trên validation
với seed 42, 7, 123. Kết quả lưu tại `outputs/results/als_seed_comparison.csv`
và `als_seed_summary.json`. Giữ mô hình seed 42, không chọn seed có điểm cao nhất.

Mô hình được chọn lưu riêng thành `outputs/models/als_tuned.npz`,
`als_tuned_ids.npz`, `als_tuned_config.json`. Mô hình ban đầu được giữ nguyên.
Điểm từng lần thử: `outputs/results/als_tuning.csv`; bảng so sánh:
`outputs/results/als_tuning_summary.json`. Kết quả đánh giá mô hình được chọn:
`outputs/results/als_tuned_validation_metrics.json`.
Đánh giá validation hỗ trợ nhiều sản phẩm đích cho mỗi người dùng, so sánh ALS
với Popularity và lưu tại `outputs/results/validation_metrics.json`.
Người dùng chưa có lịch sử train nhận điểm 0 từ ALS, được báo cáo riêng;
Popularity dùng danh sách phổ biến toàn cục. Người dùng không có sản phẩm đích
hợp lệ không nằm trong trung bình, số lượng được báo cáo rõ ràng.
Đã chốt cấu hình factors=16, regularization=0.1, alpha=5, iterations=20,
seed=42 trước khi đánh giá test. Mô hình cố định và ánh xạ lưu tại
`outputs/models/als_final.npz`, `als_final_ids.npz`; thông tin lựa chọn và
mã kiểm tra tệp nằm trong `als_final_selection.json`.
Giữ lịch sử train, không huấn luyện lại bằng validation.

Kết quả test trên 2.532 người dùng có sản phẩm đích hợp lệ:

| Mô hình | Recall@10 | NDCG@10 |
| --- | ---: | ---: |
| Popularity | 0.049335 | 0.027427 |
| ALS | 0.129641 | 0.071683 |

7 người dùng chưa có lịch sử train nhận điểm 0 từ ALS; 468 người dùng không
có sản phẩm đích hợp lệ không nằm trong trung bình. Kết quả chi tiết:
`outputs/results/als_final_test_metrics.json`, `als_final_test_per_user.csv`
và `final_test_comparison.csv`. Không dùng điểm test để chọn lại tham số.
Chưa tích hợp kết quả vào website.

`evaluation.py` chứa công thức Recall@K và NDCG@K cho nhiều sản phẩm đích.
Các file khung dưới đây chưa có logic; chưa có serving API hoặc cờ bật AI.

Giữ tên file để người tiếp nhận sắp xếp phần việc sau:

- `hybrid.py`: nơi có thể tổ chức thuật toán được lựa chọn.
- `ranking.py`, `scoring.py`: nơi có thể tổ chức xếp hạng/chấm điểm.
- `__init__.py`: đánh dấu package.

Đây chỉ là file structure, không bắt buộc dùng hybrid hoặc bất kỳ mô hình nào.
Đầu vào hiện có là product metadata, Silver events và Gold counts/sequences.
Phần tiếp theo gồm xử lý cold-start, API và kết nối UI;
xem [README gốc](../README.md) để biết định hướng hệ thống.
