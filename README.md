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

Quy trình chuẩn chỉnh để bắt đầu dự án

1. Sao chép và thiết lập cấu hình môi trường (.env):
```bash
cp .env.example .env
```
Mở file `.env` và thiết lập các tham số. 
> [!IMPORTANT]
> **Lưu ý đặc biệt cho SQL Server (MSSQL):**
> Biến `MSSQL_PASSWORD` bắt buộc phải là một **mật khẩu mạnh** (tối thiểu 8 ký tự, bao gồm ít nhất: 1 chữ hoa, 1 chữ thường, 1 chữ số, và 1 ký tự đặc biệt, ví dụ: `Admin@123456`). Nếu đặt mật khẩu yếu, container MSSQL sẽ khởi động thất bại hoặc không cho phép kết nối.

2. Khởi tạo môi trường ảo Python (Virtualenv):
```bash
make venv
```
*Lưu ý:* Thực hiện bước này ngay đầu tiên để VS Code và Pylance tự động nhận diện môi trường ảo thông qua file `.vscode/settings.json`, giúp loại bỏ hoàn toàn các lỗi gạch chân đỏ (import path) trên IDE.

3. Kiểm tra tính hợp lệ của cấu hình hệ thống:
```bash
make validate
```
Kiểm tra xem file `.env` đã đúng chưa và các cổng dịch vụ 5432, 1433, 3000 có bị ứng dụng khác chiếm dụng không.

4. Khởi chạy hạ tầng Docker (Postgres + MSSQL + Metabase + ETL):
```bash
make up
```

5. Khởi tạo Database rỗng trên Data Warehouse (PostgreSQL) và khôi phục cơ sở dữ liệu nguồn (MSSQL):
*   Tạo database DW trống trên PostgreSQL:
    ```bash
    make init-db
    ```
*   Khôi phục database nguồn AdventureWorks2022 trên SQL Server từ file backup `.bak`:
    ```bash
    make restore-db
    ```
*Lưu ý:* Cả hai lệnh này cần được chạy sau khi hạ tầng Docker ở bước 4 đã khởi chạy thành công và đạt trạng thái Healthy.

6. Kiểm tra kết nối tổng thể:
```bash
make test-conn
```
Nếu màn hình báo kết quả thành công cho cả PostgreSQL và MSSQL (như `✓ Cả hai kết nối đều thành công.`) tức là mọi thứ đã thông suốt!

---

Quy trình làm việc hàng ngày & Cách Tắt/Thoát

*   **Để bắt đầu ngày làm việc tiếp theo:**
    ```bash
    make up
    ```
*   **Khi muốn làm việc với Jupyter Notebook:**
    ```bash
    make notebook
    ```
*   **Khi muốn chạy trực tiếp chương trình ETL:**
    ```bash
    make etl
    ```
*   **Để DỪNG hoàn toàn các container Docker (khi nghỉ làm):**
    ```bash
    make down
    ```
*   **Để THOÁT khỏi môi trường ảo (Virtualenv):**
    *   Nếu bạn vào bằng lệnh `make shell`: Gõ `exit` trong terminal để thoát ra môi trường thường.
    *   Nếu bạn active bằng lệnh `source .venv/bin/activate`: Gõ `deactivate` trong terminal để tắt môi trường ảo.

---

Bộ lệnh chuẩn cho nhóm:

```bash
make validate          # kiểm tra cấu hình trước chạy (CHẠY TRƯỚC TIÊN)
make venv              # tạo virtualenv và cài đặt dependencies
make up                # khởi động các dịch vụ (chạy ngầm)
make start             # khởi động lại dịch vụ đang dừng
make stop              # dừng tạm thời các dịch vụ (giữ nguyên dữ liệu)
make restart           # khởi động lại các dịch vụ
make down              # dừng hoàn toàn và gỡ bỏ các container
make down-v            # dừng các dịch vụ và xoá toàn bộ volume dữ liệu
make clean             # dọn dẹp sạch sẽ container và volumes
make init-db           # tạo databases postgres (chỉ cần chạy 1 lần đầu)
make restore-db        # khôi phục database AdventureWorks2022 trên MSSQL
make test-conn         # kiểm tra kết nối DB từ Python
make etl               # chạy trực tiếp pipeline ETL chính
make notebook          # mở Jupyter Lab phục vụ phân tích
make shell             # vào môi trường ảo Python tương tác (gõ 'exit' để thoát)
make psql              # mở shell psql bên trong container postgres
make logs              # xem logs real-time của Docker
make ps                # xem trạng thái hoạt động của các containers
make requirements-check # kiểm tra các package cũ cần cập nhật
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
