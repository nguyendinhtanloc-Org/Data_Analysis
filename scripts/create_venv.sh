#!/usr/bin/env bash
set -e

# Tạo virtualenv riêng cho dự án để không ảnh hưởng Python hệ thống.
python3 -m venv .venv
source .venv/bin/activate

# Nâng pip trước khi cài dependency để giảm lỗi cài đặt.
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Virtual environment created and dependencies installed. Activate with: source .venv/bin/activate"