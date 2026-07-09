#!/bin/bash
# Script để khôi phục cơ sở dữ liệu AdventureWorks2022 từ file backup.

set -e

# Load biến môi trường từ .env nếu có
if [ -f .env ]; then
    export $(cat .env | grep -v '#' | awk '/=/ {print $1}')
fi

MSSQL_PASSWORD=${MSSQL_PASSWORD:-"YourStrong@Passw0rd"}
BACKUP_FILE="/var/opt/mssql/backup/AdventureWorks2022.bak"
DB_NAME="AdventureWorks2022"

echo "Đang chờ SQL Server khởi động hoàn tất..."
sleep 15

echo "Bắt đầu khôi phục cơ sở dữ liệu ${DB_NAME} từ ${BACKUP_FILE}..."

docker compose exec -T mssql /opt/mssql-tools18/bin/sqlcmd \
    -S localhost -U sa -P "${MSSQL_PASSWORD}" -C \
    -Q "RESTORE DATABASE [${DB_NAME}] FROM DISK = N'${BACKUP_FILE}' WITH MOVE 'AdventureWorks2022' TO '/var/opt/mssql/data/AdventureWorks2022.mdf', MOVE 'AdventureWorks2022_log' TO '/var/opt/mssql/data/AdventureWorks2022_log.ldf', REPLACE, STATS = 5"

echo "Khôi phục hoàn tất."
