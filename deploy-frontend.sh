#!/bin/bash
# 部署前端到服务器

set -e

echo "🔨 构建前端..."
npm run build

echo "📦 同步到服务器..."
rsync -avz --delete dist/ranking/ tencent-nofx:/home/ubuntu/nofx-Metroll/dist/ranking/

echo "✅ 部署完成"
echo "🌐 访问: http://43.128.147.27/ranking/"
