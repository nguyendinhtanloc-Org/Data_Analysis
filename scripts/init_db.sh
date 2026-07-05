#!/usr/bin/env bash
set -e

# Khởi tạo Data Warehouse và Metabase database nếu chưa tồn tại
HOST=${POSTGRES_HOST:-localhost}
PORT=${POSTGRES_PORT:-5432}

PGUSER=${POSTGRES_USER:-postgres}
PGPASSWORD=${POSTGRES_PASSWORD:-postgres}

DB=${POSTGRES_DB:-adventureworks_dw}
METADB=${METABASE_DB_DBNAME:-metabase_db}

export PGPASSWORD

# Chờ PostgreSQL sẵn sàng
until pg_isready -h "$HOST" -p "$PORT" -U "$PGUSER" >/dev/null 2>&1; do
    echo "Waiting for PostgreSQL at $HOST:$PORT..."
    sleep 2
done

echo "Kiểm tra và tạo database nếu chưa tồn tại..."

# Kiểm tra database đã tồn tại hay chưa
exists_db() {
    local dbname="$1"

    psql \
        -h "$HOST" \
        -p "$PORT" \
        -U "$PGUSER" \
        -d postgres \
        -tAc "SELECT 1 FROM pg_database WHERE datname='${dbname}'"
}

# Tạo Data Warehouse database
if [ "$(exists_db "$DB")" = "1" ]; then
    echo "Database '$DB' đã tồn tại — bỏ qua tạo."
else
    echo "Tạo database '$DB'..."

    psql \
        -h "$HOST" \
        -p "$PORT" \
        -U "$PGUSER" \
        -d postgres \
        -v ON_ERROR_STOP=1 \
        -c "CREATE DATABASE \"$DB\";"
fi

# Tạo Metabase database
if [ "$(exists_db "$METADB")" = "1" ]; then
    echo "Database '$METADB' đã tồn tại — bỏ qua tạo."
else
    echo "Tạo database '$METADB'..."

    psql \
        -h "$HOST" \
        -p "$PORT" \
        -U "$PGUSER" \
        -d postgres \
        -v ON_ERROR_STOP=1 \
        -c "CREATE DATABASE \"$METADB\";"
fi

# Khởi tạo schema và các bảng DWH
echo "Khởi tạo schema và các bảng DWH từ ddl_script.sql..."

if [ -f /tmp/ddl_script.sql ]; then
    psql \
        -h "$HOST" \
        -p "$PORT" \
        -U "$PGUSER" \
        -d "$DB" \
        -v ON_ERROR_STOP=1 \
        -f /tmp/ddl_script.sql
else
    echo "Cảnh báo: Không tìm thấy /tmp/ddl_script.sql"
fi

echo "Hoàn tất kiểm tra và khởi tạo database."