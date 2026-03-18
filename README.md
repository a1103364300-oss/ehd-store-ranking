# 🏆 易惠达门店日排行系统

便利店连锁门店的每日订单排行榜系统，支持多门店排名对比、历史趋势查看、权限管理。

## 在线访问

- 排行榜首页：`http://你的服务器IP/ranking/`
- 管理后台：`http://你的服务器IP/ranking/admin.html`
- 门店详情：`http://你的服务器IP/ranking/store.html?name=门店名&date=2026-03-18`

## 功能一览

| 功能 | 说明 |
|------|------|
| 🏅 门店排行榜 | 每日全量门店排名，前三名颁奖台展示 |
| 📅 历史日期切换 | 可查看过去任意一天的排名 |
| 📊 门店详情 | 单店订单趋势图、历史排名 |
| 🔐 权限管理 | 管理员看全部，普通用户只看授权门店 |
| 👥 邻居门店 | 有限权限用户可看到相邻排名的门店 |
| 🎫 邀请码注册 | 通过邀请卡注册新用户 |
| 📈 利润分析 | 门店利润数据分析（需权限） |
| 🌙 深色/浅色主题 | 支持主题切换 |
| 📱 移动端适配 | 手机端可正常使用 |

## 技术栈

- **后端**：Python FastAPI + SQLite
- **前端**：单文件 HTML（无框架，直接部署）
- **认证**：JWT（7天有效期）
- **部署**：nginx 反向代理

## 项目结构

```
ehd-store-ranking/
├── backend/
│   └── main.py              # FastAPI 后端（API + 认证 + 数据查询）
├── server-ui-v2/
│   ├── index-ui-v2.html     # 排行榜首页（当前线上版）
│   ├── admin-ui-v2.html     # 管理后台（当前线上版）
│   ├── store-original.html  # 门店详情页
│   ├── index-original.html  # 首页原版备份
│   └── admin-original.html  # 后台原版备份
├── update_ranking.py        # 数据同步脚本
└── README.md
```

## 快速部署

### 1. 环境准备

需要 Python 3.10+，安装依赖：

```bash
pip install fastapi uvicorn python-jose[cryptography] passlib[bcrypt] pydantic
```

### 2. 准备数据库

系统使用两个 SQLite 数据库：

| 数据库 | 路径 | 用途 |
|--------|------|------|
| 认证库 | `~/ranking_auth.db` | 用户、邀请卡（自动创建） |
| 业务库 | `~/qnh-data/qnh.db` | 门店订单数据（需提前导入） |

业务库的核心表结构：

```sql
-- store_daily_full 表（每日门店数据）
CREATE TABLE store_daily_full (
    date TEXT,           -- 日期，如 '2026-03-18'
    store_name TEXT,     -- 门店名称
    valid_orders INTEGER,-- 有效订单数
    sales_revenue REAL,  -- 销售额
    refund_orders INTEGER,-- 退款订单数
    new_customers INTEGER,-- 新客数
    old_customers INTEGER,-- 老客数
    merchant_discount REAL,-- 商家优惠
    platform_subsidy REAL -- 平台补贴
);
```

### 3. 启动后端

```bash
cd backend
python3 -m uvicorn main:app --host 127.0.0.1 --port 8899
```

后台运行：

```bash
nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 8899 > server.log 2>&1 &
```

### 4. 部署前端

把前端 HTML 文件放到 nginx 可访问的目录：

```bash
# 示例：复制到 nginx 静态目录
cp server-ui-v2/index-ui-v2.html /你的nginx目录/ranking/index.html
cp server-ui-v2/admin-ui-v2.html /你的nginx目录/ranking/admin.html
cp server-ui-v2/store-original.html /你的nginx目录/ranking/store.html
```

### 5. 配置 nginx

```nginx
# 静态文件
location /ranking/ {
    alias /你的nginx目录/ranking/;
    index index.html;
}

# API 反向代理
location /ranking/api/ {
    proxy_pass http://127.0.0.1:8899/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

重载 nginx：

```bash
nginx -s reload
```

### 6. 首次登录

系统启动后会自动创建管理员账号：

- 用户名：`admin`
- 密码：`Admin2026!`

**请登录后立即修改密码。**

## API 接口

所有接口需要在 Header 中携带 JWT：

```
Authorization: Bearer <token>
```

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/login` | 登录，返回 token |
| POST | `/api/register` | 注册（需邀请卡号） |
| GET | `/api/me` | 获取当前用户信息 |

### 排行榜

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ranking?date=2026-03-18` | 获取指定日期排名 |
| GET | `/api/available-dates` | 获取有数据的日期列表 |
| GET | `/api/store-history?name=门店名` | 获取门店历史数据 |

### 管理（需管理员权限）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/generate-cards` | 生成邀请卡 |
| GET | `/api/admin/cards` | 查看邀请卡列表 |
| GET | `/api/admin/users` | 查看用户列表 |
| POST | `/api/admin/set-permissions` | 设置门店权限 |

## 权限模型

```
管理员（is_admin=1）
  └── 可查看所有门店、管理用户、生成邀请卡

普通用户（有 store_permissions）
  └── 只能查看授权门店 + 相邻排名的邻居门店

普通用户（无 store_permissions）
  └── 提示"未配置权限，请联系管理员"
```

## 邀请卡

- 格式：`EHD-XXXX-XXXX`
- 每张只能使用一次
- 在管理后台生成和管理

## 常见问题

### Q: 页面打开白屏 / 接口 502
**A**: 检查后端是否在正确端口运行：

```bash
# 检查进程
ps aux | grep 8899

# 检查端口
netstat -tlnp | grep 8899

# 如果没有，重新启动
cd /你的后端目录
nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 8899 > server.log 2>&1 &
```

### Q: 登录后显示"未配置权限"
**A**: 管理员需要在后台为该用户分配门店权限：
1. 登录管理后台
2. 点击"门店权限"
3. 选择用户，勾选门店，保存

### Q: 排行榜没有数据
**A**: 检查业务数据库是否有对应日期的数据：

```bash
sqlite3 ~/qnh-data/qnh.db "SELECT DISTINCT date FROM store_daily_full ORDER BY date DESC LIMIT 5;"
```

### Q: 如何导入新的门店数据
**A**: 将牵牛花导出的经营详情 Excel 通过导入脚本写入数据库，然后排行榜会自动显示新数据。

## 开发说明

本项目采用单文件 HTML 架构，修改前端后直接替换服务器文件即可生效，无需构建步骤。

如需本地开发调试，可以用 Python 起一个简单的静态服务器：

```bash
cd server-ui-v2
python3 -m http.server 5050
```

然后访问 `http://127.0.0.1:5050/index-ui-v2.html`（注意：需要后端 API 才能看到数据）。

## License

MIT
