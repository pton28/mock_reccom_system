# Khung dành cho người cộng tác

Các file Python trong thư mục này **rỗng**, không được ứng dụng import.
Không có thuật toán, train/evaluate, artifacts, serving API hoặc cờ bật AI.

Giữ tên file để người tiếp nhận sắp xếp phần việc sau:

- `hybrid.py`: nơi có thể tổ chức thuật toán được lựa chọn.
- `ranking.py`, `scoring.py`: nơi có thể tổ chức xếp hạng/chấm điểm.
- `evaluation.py`: nơi có thể tổ chức đánh giá.
- `__init__.py`: đánh dấu package.

Đây chỉ là file structure, không bắt buộc dùng hybrid hoặc bất kỳ mô hình nào.
Đầu vào hiện có là product metadata, Silver events và Gold counts/sequences.
Người cộng tác tự thiết kế features, chia tập theo thời gian, train, evaluation,
lưu/load model, API và kết nối UI; xem [README gốc](../README.md).
