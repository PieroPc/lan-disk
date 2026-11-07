#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
  echo "未找到 python3，请先安装 Python 3.9+"
  exit 1
fi

if ! $PY -c "import fastapi, uvicorn, multipart" >/dev/null 2>&1; then
  echo "首次运行，安装依赖..."
  $PY -m pip install -r requirements.txt
fi

# 如需口令 / 换端口，可在此导出环境变量
# export LAN_DISK_PASSWORD=123456
# export LAN_DISK_PORT=9000

exec $PY main.py "$@"
