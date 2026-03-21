#!/bin/bash
# 重启排行榜后端

cd /home/ubuntu/ranking-backend

# 停止旧进程
pkill -f "uvicorn main:app.*8899" 2>/dev/null || true
sleep 1

# 启动新进程
cd backend
nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 8899 > ../server.log 2>&1 &

sleep 2
if netstat -tlnp 2>/dev/null | grep -q 8899; then
    echo "✅ 后端已启动 (端口 8899)"
else
    echo "❌ 启动失败，请检查 server.log"
fi
