#!/usr/bin/env bash
set -e

# Xoá thư mục .venv cũ nếu có để tránh lỗi cài đặt dở dang/hỏng file cert
rm -rf .venv

# Tạo virtualenv riêng cho dự án để không ảnh hưởng Python hệ thống.
python3 -m venv .venv
source .venv/bin/activate

# Cài đặt dependency trực tiếp bằng pip mặc định của venv (tránh lỗi hỏng file cert khi nâng cấp pip)
pip install -r requirements.txt

echo "Virtual environment created and dependencies installed. Activate with: source .venv/bin/activate"