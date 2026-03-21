#!/bin/bash
# 本地开发启动脚本（仅后端 API）

set -e

cd ~/clawd/projects/store-ranking

# 激活虚拟环境
source .venv/bin/activate

echo "🚀 启动本地后端 API..."
echo ""
echo "📍 API 地址: http://127.0.0.1:8899"
echo "📍 测试命令:"
echo "   curl http://127.0.0.1:8899/api/ranking"
echo "   curl 'http://127.0.0.1:8899/api/ranking?date=2026-03-20'"
echo ""
echo "注意: 前端页面在服务器上测试"
echo "      本地只测试后端 API"
echo ""
echo "按 Ctrl+C 停止"
echo ""

cd backend
python3 -m uvicorn main:app --host 127.0.0.1 --port 8899 --reload
