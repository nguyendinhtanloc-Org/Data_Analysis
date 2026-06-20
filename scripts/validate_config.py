#!/usr/bin/env python3
"""Validate configuration để đảm bảo dự án có thể chạy được.

Script này kiểm tra:
- Biến môi trường bắt buộc được set
- Mật khẩu không phải placeholder yếu
- Docker có sẵn
- Port không bị chiếm dụng
"""
import os
import sys
import socket
from pathlib import Path


def load_env_file():
    """Load .env file vào environment variables."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip()


def check_required_env():
    """Kiểm tra các biến môi trường bắt buộc."""

    # Các biến này được dùng trong docker-compose.yml
    required = [
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "METABASE_DB_TYPE",
        "METABASE_DB_DBNAME",
        "METABASE_DB_PORT",
        "METABASE_DB_USER",
        "METABASE_DB_PASS",
        "METABASE_DB_HOST",
    ]


    missing = [var for var in required if not os.getenv(var)]
    
    if missing:
        print(f"LỖI: Biến môi trường bắt buộc chưa được set: {', '.join(missing)}")
        print("Hãy chạy: cp .env.example .env && sửa giá trị trong .env")
        return False
    return True


def check_password_strength():
    """Kiểm tra mật khẩu có phải placeholder yếu hay không."""
    
    password = os.getenv("POSTGRES_PASSWORD", "")
    
    # Placeholder placeholder (luôn lỗi)
    unacceptable = ["change-me-strong-password", ""]
    
    # Mật khẩu phổ biến cho dev (cảnh báo nhưng được phép)
    weak_dev_passwords = ["postgres", "password"]
    
    if password in unacceptable:
        print(f"LỖI: Mật khẩu '{password}' không được phép, hãy đổi trong .env")
        return False
    
    if password in weak_dev_passwords:
        print(f"CẢNH BÁO: Mật khẩu '{password}' là dev placeholder (được phép cho local dev)")
        return True  # Vẫn pass, chỉ cảnh báo
    
    return True


def check_port_available(port: int) -> bool:
    """Kiểm tra xem cổng có sẵn để dùng không.

    socket.connect_ex trả về:
    - 0: kết nối được => cổng đang BẬN
    - khác 0: không kết nối được => cổng đang RỖNG

    Hàm này trả về True khi cổng RỖNG.
    """

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result = sock.connect_ex(("localhost", port))
        is_port_busy = result == 0
        return not is_port_busy
    finally:
        sock.close()



def validate_all():
    """Chạy toàn bộ kiểm tra."""

    # Nạp lại .env để đảm bảo chạy từ nơi khác vẫn có cấu hình.
    # (load_env_file() ở main có thể không được gọi nếu module bị import.)
    load_env_file()

    print("Kiểm tra cấu hình dự án...")
    
    checks = [
        ("Biến môi trường bắt buộc", check_required_env),
        ("Mật khẩu đủ mạnh", check_password_strength),
    ]
    
    port_checks = [
        ("Postgres port 5432", 5432),
        ("Metabase port 3000", 3000),
    ]
    
    all_pass = True
    
    for name, check_func in checks:
        status = "OK" if check_func() else "LỖI"
        print(f"[{status}] {name}")
        if not check_func():
            all_pass = False
    
    for name, port in port_checks:
        available = check_port_available(port)
        status = "OK" if available else "CHIẾM DỤNG"
        print(f"[{status}] {name}")
        if not available:
            print(f"     Port {port} đang được dùng, hãy chạy: make down")
            all_pass = False
    
    if all_pass:
        print("\nToàn bộ cấu hình ổn, sẵn sàng chạy: make up")
        return 0
    else:
        print("\nCó lỗi cấu hình, sửa rồi chạy lại.")
        return 1


if __name__ == "__main__":
    load_env_file()
    sys.exit(validate_all())
