# Luồng Code của Platform Engineer (DevOps & Infrastructure)

## Giới thiệu

Người Platform Engineer chịu trách nhiệm thiết lập và vận hành cơ sở hạ tầng: container hóa với Docker, điều phối dịch vụ với docker-compose, khởi tạo CSDL, kiểm tra cấu hình, và triển khai CI/CD.

## Các file liên quan

| File | Mục đích |
|------|----------|
| `Dockerfile` | Dựng ảnh ETL container (Python 3.11-slim) |
| `docker-compose.yml` | Định nghĩa 4 dịch vụ: postgres, mssql, etl, metabase |
| `Makefile` | Trung tâm điều khiển (17 target) |
| `scripts/init_db.sh` | Khởi tạo database PostgreSQL + chạy DDL |
| `scripts/init_dw_tables.py` | Python DDL cho dw/mart schema |
| `scripts/validate_config.py` | Kiểm tra cấu hình trước khi chạy |
| `scripts/restore_mssql.sh` | Phục hồi dữ liệu mẫu AdventureWorks vào MSSQL |
| `scripts/create_venv.sh` | Tạo virtual env (development) |
| `.env.example` | Mẫu template cho biến môi trường |
| `config.json` | Cấu hình runtime: watermarks, last_run, snapshot_watermark |
| `sql/ddl_script.sql` | DDL bản SQL (thông qua init_db.sh) |
| `pyproject.toml` | Metadata dự án + cấu hình pytest |
| `requirements.txt` | Danh sách pip dependencies |
| `.github/workflows/ci.yml` | CI pipeline (GitHub Actions) |

## Cách chạy

```bash
# Khởi tạo toàn bộ hệ thống
make validate         # Kiểm tra cấu hình
make up               # docker compose up -d
make init-db          # Tạo DB + chạy DDL
make test-conn        # Kiểm tra kết nối

# ETL
make etl              # Incremental load
make etl-full         # Full load

# ML
make ml               # Chạy toàn bộ ML modules

# Analytics
make snapshot         # KPI snapshot
make analytics-runner period=2014Q2

# Quản lý container
make down             # Tắt container
make down-v           # Tắt container + xoá volume
make logs             # Xem log
make shell            # Bash vào container ETL
```

## Kiến trúc Docker

### Dockerfile

`Dockerfile` xây dựng image cho container ETL:

```
Python 3.11-slim
  --> apt-get install: gcc, g++, gfortran, libopenblas-dev, liblapack-dev,
                        unixodbc-dev, curl
  --> pip install --upgrade pip
  --> COPY requirements.txt, pyproject.toml
  --> pip install -r requirements.txt
  --> COPY toàn bộ source code
  --> ENV PYTHONPATH=/app
  --> Tạo user non-root (appuser, uid=1001)
  --> HEALTHCHECK: python -c "import sys; from src.config import load_postgres_settings"
  --> CMD: tail -f /dev/null (container sống để thực thi lệnh exec)
```

Image được build bằng `docker compose build etl`. Cần rebuild sau mỗi thay đổi source code.

### Docker Compose Architecture

`docker-compose.yml` định nghĩa 4 dịch vụ trên cùng network `warehouse_net`:

1. **postgres** (Data Warehouse):
   - Image: `postgres:16-alpine`
   - Port: `127.0.0.1:5432:5432`
   - Volume: `postgres_data` (persistent)
   - Healthcheck: `pg_isready -U admin -d adventureworks_dw`
   - Resource: memory=512M
   - Env: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB từ .env

2. **mssql** (OLTP - AdventureWorks):
   - Image: `mcr.microsoft.com/mssql/server:2022-latest`
   - Port: `127.0.0.1:1433:1433`
   - Volume: `mssql_data` + `./data:/var/opt/mssql/backup`
   - Healthcheck: `/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -Q "SELECT 1"`
   - Resource: memory=2G
   - Platform: `linux/amd64`
   - Env: ACCEPT_EULA, SA_PASSWORD từ .env

3. **etl** (Python ETL):
   - Build từ Dockerfile
   - Volume mount: `./:/app` (development, cho phép thay đổi code mà không cần rebuild)
   - Env: PYTHONUNBUFFERED=1, các biến từ .env
   - Resource: memory=1G
   - Depends on: postgres (healthy), mssql (healthy)
   - HEALTHCHECK: python import check

4. **metabase** (BI Dashboard):
   - Image: `metabase/metabase:v0.50.1`
   - Port: `127.0.0.1:3000:3000`
   - Env: MB_DB_TYPE=postgres, MB_DB_DBNAME=metabase_db, ...
   - Resource: memory=1G
   - Depends on: postgres (healthy)
   - Security: MB_SESSION_COOKIE_SAMESITE=lax, MB_PASSWORD_COMPLEXITY=strong

## Makefile Target Groups

### Infrastructure targets

| Target | Command | Mô tả |
|--------|---------|-------|
| `up` | `docker compose up -d` | Khởi động tất cả container |
| `down` | `docker compose down` | Tắt container |
| `down-v` | `docker compose down -v` | Tắt + xoá volume |
| `build` | `docker compose build` | Build image ETL |
| `rebuild` | `docker compose build --no-cache` | Build không dùng cache |
| `logs` | `docker compose logs -f` | Follow log |
| `ps` | `docker compose ps` | Trạng thái container |

### Database targets

| Target | Mô tả |
|--------|-------|
| `init-db` | Copy `init_db.sh` và `ddl_script.sql` vào container postgres, tạo database adventureworks_dw và metabase_db, chạy DDL |
| `restore-db` | Gọi `scripts/restore_mssql.sh` để restore AdventureWorks vào MSSQL |
| `psql` | Mở psql trong container postgres |
| `shell-postgres` | Bash vào container postgres |

### ETL targets

| Target | Mô tả |
|--------|-------|
| `etl` | `python src/etl/etl.py` (incremental, auto-detect first run) |
| `etl-full` | `python src/etl/etl.py --full` |
| `test-conn` | `python src/etl/etl.py --test` |
| `validate` | `python scripts/validate_config.py` |

### ML targets

| Target | Mô tả |
|--------|-------|
| `ml-clustering` | RFM customer segmentation |
| `ml-anomaly` | Inventory anomaly detection |
| `ml-decision` | Decision support engine |
| `ml-migration` | Customer migration tracking |
| `ml-early-warning` | Early warning system |
| `ml` | clustering + anomaly + migration + decision |

### Analytics targets

| Target | Mô tả |
|--------|-------|
| `snapshot` | KPI snapshot (quarterly) |
| `analytics-kpi` | Chỉ tính KPI |
| `analytics-contribution` | Phân tích đóng góp |
| `analytics-drilldown` | Drill-down diagnosis |
| `analytics-causal` | Price elasticity |
| `analytics-all` | Tất cả analytics modules |
| `analytics-runner` | Báo cáo đầy đủ (Markdown) |

## Quy trình khởi tạo lần đầu

Bước 1: Clone repo và copy .env
```bash
git clone <repo>
cp .env.example .env
# Sửa .env: đặt password mạnh
```

Bước 2: Kiểm tra cấu hình
```bash
make validate
```
`validate_config.py` kiểm tra:
- Tất cả biến môi trường cần thiết đã được đặt
- Password MSSQL đạt yêu cầu độ mạnh (tối thiểu 8 ký tự, có ký tự đặc biệt)
- Cổng không bị conflict
- File config.json tồn tại và hợp lệ

Bước 3: Khởi động container
```bash
make up
```
Docker compose khởi động 4 container theo thứ tự:
- postgres (healthcheck: pg_isready)
- mssql (healthcheck: sqlcmd SELECT 1)
- etl (healthcheck: python import check, depend on postgres + mssql)
- metabase (depend on postgres)

Bước 4: Khởi tạo database
```bash
make init-db
```
`init_db.sh` thực hiện:
- Kiểm tra `adventureworks_dw` đã tồn tại chưa
- Tạo `metabase_db` nếu chưa có
- Chạy `sql/ddl_script.sql` để tạo:
  - Schema: dw, staging, mart
  - 7 bảng dw.* + indexes
  - 8 bảng mart.* + indexes
  - Daily sales agg table + index

Bước 5: Kiểm tra kết nối
```bash
make test-conn
```

Bước 6: Restore dữ liệu mẫu
```bash
make restore-db
```
`restore_mssql.sh` thực hiện:
- Tải file backup AdventureWorks2022.bak từ URL
- Copy vào container mssql
- Chạy lệnh RESTORE DATABASE trong MSSQL

Bước 7: Full load ETL
```bash
make etl-full
```

Bước 8: Chạy ML
```bash
make ml
```

Bước 9: Chạy analytics
```bash
make analytics-runner period=2014Q2
```

## CI/CD Pipeline

File `.github/workflows/ci.yml` định nghĩa GitHub Actions workflow:

1. **lint**: Kiểm tra Python syntax
2. **test**: Chạy pytest
   - tests/test_anomaly.py: 6 tests
   - tests/test_clustering.py: 5 tests
   - tests/test_config.py: 2 tests
   - tests/test_counterexamples.py: 12 tests
   - tests/test_decision_support.py: (pre-existing failure)
   - tests/test_early_warning.py: (pre-existing failure)
   - tests/test_integration.py: 8 tests (cần DB connection)
   - tests/test_migration.py: (pre-existing failure)
   - tests/test_transform.py: (pre-existing failure)
3. **schema-check**: So sánh số lượng `CREATE TABLE` giữa `sql/ddl_script.sql` và `scripts/init_dw_tables.py`. Nếu lệch, fail build.
4. **build**: Docker build (đảm bảo image build được)

## Cấu hình quản lý

### .env (biến môi trường)

Chứa thông tin nhạy cảm: database credentials, host, port.
File này KHÔNG được commit vào git (trong .gitignore).

### config.json (runtime state)

File này được đọc/ghi trong lúc chạy:
- `watermarks`: dictionary table_name -> watermark datetime
- `last_run`: thời gian chạy gần nhất
- `last_run_status`: SUCCESS hoặc FAILED
- `snapshot_watermark`: period key gần nhất đã snapshot

File này có file locking (`fcntl.flock`) để đảm bảo an toàn khi nhiều tiến trình đọc/ghi đồng thời.

### pyproject.toml

Cấu hình dự án Python:
- `[project]`: name, version, dependencies
- `[tool.pytest.ini_options]`: testpaths = ["tests"]
- Backend: setuptools
