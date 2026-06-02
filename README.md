# Data_Analysis

# Data_Analysis

Dự án: Kho Dữ liệu & Phân tích Doanh nghiệp (Data Warehouse & Business Analytics)

Khung dự án đã được khởi tạo sẵn, tuân thủ các tiêu chuẩn an toàn và sạch code của DA/DE hiện nay.

Cấu trúc chính:

- `data/raw`, `data/processed`, `data/external` — lưu dữ liệu theo quy ước
- `notebooks/` — các phân tích và kiểm tra
- `src/` — mã nguồn ETL và cấu hình chung
- `reports/figures` — đầu ra phân tích
- `tests/` — test case cho ETL
- `sql/` — các script SQL cho schema

Quy trình an toàn để bắt đầu

1. Sao chép cấu hình mẫu thành `.env` thực tế:

```bash
cp .env.example .env
```

2. Sửa mật khẩu trong `.env` thành giá trị mạnh (không dùng placeholder):

Mở file `.env` và đổi `POSTGRES_PASSWORD` và `METABASE_DB_PASS` thành giá trị của bạn.

Nếu chỉ dùng cho dev local, có thể dùng mật khẩu đơn giản (ví dụ: `postgres`) - script validate sẽ cảnh báo nhưng vẫn cho phép.

**Lưu ý:** Phải sửa `.env` XONG trước khi chạy `make validate` ở bước 3.

3. Kiểm tra cấu hình (sau khi .env đã sửa):

```bash
make validate
```

Nếu validate báo lỗi, hãy kiểm tra:
- `.env` file đã tồn tại chưa?
- Mật khẩu trong `.env` đã sửa thành giá trị mạnh chưa (không để placeholder)?
- Ports 5432 và 3000 có bị chiếm không?

4. Khởi chạy hạ tầng (Postgres + Metabase):

```bash
make up
```

5. Tạo môi trường Python:

```bash
make venv
```

Để vào venv shell tương tác (không cần `source` thủ công):

```bash
make shell
# Sau đó bạn ở trong virtualenv, có thể chạy python, pip, etc
```

6. Tạo DB và kiểm tra kết nối:

```bash
make init-db
make test-conn
```

Bộ lệnh chuẩn cho nhóm:

```bash
make validate          # kiểm tra cấu hình trước chạy (CHẠY TRƯỚC TIÊN)
make up                # khởi động services
make start             # khởi động services đang dừng
make stop              # dừng services
make restart           # khởi động lại services
make down              # dừng services
make down-v            # dừng services và xoá volume
make build             # build images
make rebuild           # build lại không dùng cache
make clean             # dừng services và xoá volume
make logs              # xem logs real-time
make ps                # xem trạng thái container
make venv              # tạo virtualenv
make shell             # vào virtualenv shell (thay vì source)
make init-db           # tạo database
make test-conn         # kiểm tra kết nối
make shell-postgres    # vào shell container postgres
make psql              # mở psql trong container postgres
make notebook          # mở Jupyter Lab
make requirements-check # kiểm tra packages outdated
```

Lưu ý về môi trường:

- Khi chạy lệnh từ máy local, `POSTGRES_HOST` phải là `localhost`.
- Khi chạy giữa các container trong Docker Compose, host là `postgres`.
- Mật khẩu trong `.env.example` chỉ là placeholder, không dùng để triển khai thật.
- Nếu file `.env` cũ đang để `POSTGRES_HOST=postgres`, hãy đổi lại `localhost` cho các lệnh chạy từ máy host.
- Luôn chạy `make validate` trước `make up` để kiểm tra cấu hình.
- File `.env` KHÔNG được commit vào Git; dùng `.env.example` làm template thôi.

Tiêu chuẩn bảo mật dự án:

- Tất cả mật khẩu phải được set trong `.env`, không hardcode trong code.
- Mật khẩu development phải khác với production.
- Version của Docker image được pin cụ thể (ví dụ `postgres:15`, không dùng `latest`).
- Các package Python được pin version để đảm bảo reproducibility.
- Secret files (`.env`) được thêm vào `.gitignore`.

Tập tin quan trọng:

- `docker-compose.yml` — cấu hình hạ tầng, sử dụng biến env để tránh hardcode
- `.env.example` — template biến môi trường
- `requirements.txt` — danh sách package Python cùng phiên bản pin
- `src/config.py` — gom logic đọc env và tạo connection string
- `src/etl.py` — skeleton ETL chính, dùng config.py
- `scripts/validate_config.py` — kiểm tra cấu hình trước chạy
- `notebooks/SETUP.md` — hướng dẫn import chung cho notebook

Bắt đầu phần kỹ thuật tiếp theo:

Sau khi môi trường sẵn sàng, nhóm có thể chia công việc theo vai trò:
- A: Data Architect — viết schema SQL và tạo DDL
- B: ETL Engineer — hiện thực extract/transform/load
- C: Analytics Engineer — viết notebook phân tích Q1–Q5
- D: BI & Reporting — tạo dashboard Metabase