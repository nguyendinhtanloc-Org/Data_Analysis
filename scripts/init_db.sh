#!/usr/bin/env bash
set -e
# Wait for Postgres to be ready then create needed DBs and user
HOST=${POSTGRES_HOST:-localhost}
PORT=${POSTGRES_PORT:-5432}
USER=${POSTGRES_USER:-postgres}
PASS=${POSTGRES_PASSWORD:-postgres}
DB=${POSTGRES_DB:-adventureworks}
METADB=${METABASE_DB_DBNAME:-metabase_db}

export PGPASSWORD="$PASS"

until pg_isready -h "$HOST" -p "$PORT" -U "$USER" >/dev/null 2>&1; do
  echo "Waiting for Postgres at $HOST:$PORT..."
  sleep 2
done

echo "Kiểm tra và tạo database nếu chưa tồn tại..."

exists_db() {
  local dbname="$1"
  psql -h "$HOST" -p "$PORT" -U "$USER" -tAc "SELECT 1 FROM pg_database WHERE datname='${dbname}'" 2>/dev/null
}

if [ "$(exists_db "$DB")" = "1" ]; then
  echo "Database '$DB' đã tồn tại — bỏ qua tạo."
else
  echo "Tạo database '$DB'..."
  psql -h "$HOST" -p "$PORT" -U "$USER" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$DB\";"
fi

if [ "$(exists_db "$METADB")" = "1" ]; then
  echo "Database '$METADB' đã tồn tại — bỏ qua tạo."
else
  echo "Tạo database '$METADB'..."
  psql -h "$HOST" -p "$PORT" -U "$USER" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$METADB\";"
fi

echo "Khởi tạo schema và các bảng DWH từ sql/ddl_script.sql..."
if [ -f sql/ddl_script.sql ]; then
  psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -f sql/ddl_script.sql
else
  echo "Cảnh báo: Không tìm thấy sql/ddl_script.sql"
fi

echo "Hoàn tất kiểm tra/khởi tạo database."
