# 给 AI Agent 的项目说明

> 如果你是一个 AI Agent（Codex / Claude Code / 其他），这是你需要知道的。

## 一、这是什么项目

**易惠达门店排行系统**：展示门店每日经营排行，支持多用户权限管理。

**核心功能**：
1. 排行榜展示（按有效订单数排名）
2. 用户权限管理（管理员 / 普通用户 / 有限权限）
3. 门店历史趋势查看
4. CLI 工具用于排障和查询

---

## 二、技术边界

| 你应该知道 | 说明 |
|---|---|
| 前端 | React 19 + Vite + Tailwind，构建后部署到 `/ranking/` 子路径 |
| 后端 | FastAPI + SQLite，跑在 8899 端口 |
| 数据源 | `store_daily_full` 表，来自牵牛花系统 |
| 权限 | JWT + 邀请码，管理员可看全部，普通用户可限制门店 |
| 同步 | 排行系统同步的是 `qnh.db`，**不是** `data.json` |

---

## 三、常见任务指南

### 如果要改前端

1. 改 `src/` 下的代码
2. `npm run build` 构建到 `dist/`
3. 部署时 `dist/` 内容放到服务器 `/home/ubuntu/nofx-Metroll/dist/ranking/`

### 如果要改后端

1. 改 `backend/main.py`
2. 本地测试：`python3 backend/main.py`
3. 服务器重启后端服务

### 如果要改 CLI

1. 改 `backend/ranking_cli.py`
2. CLI 是只读工具，不碰写操作
3. 所有命令支持 `--json` 输出

### 如果要排障

```bash
# 最常用的三条
python3 backend/ranking_cli.py health
python3 backend/ranking_cli.py server ports
python3 backend/ranking_cli.py db latest-date
```

---

## 四、数据库路径约定

**本地开发环境**：
- 认证库：`~/ranking_auth.db`（可能不存在）
- 业务库：`~/qnh-data/qnh.db`

**服务器环境**：
- 认证库：`/home/ubuntu/ranking_auth.db`
- 业务库：`/home/ubuntu/qnh-data/qnh.db`

CLI 会自动探测，也可以用环境变量覆盖：

```bash
RANKING_AUTH_DB=/path/to/ranking_auth.db
RANKING_QNH_DB=/path/to/qnh.db
```

---

## 五、重要约束

1. **不要改 `store_daily_full` 的写入逻辑** —— 数据来自牵牛花导出，这个项目只读
2. **不要把后端跑在 8898 端口** —— nginx 反代的是 8899
3. **前端构建时 `base: '/ranking/'`** —— 子路径部署
4. **用户权限是 JSON 数组** —— `store_permissions` 字段，空数组 = 全部门店可见

---

## 六、已知问题

- `ranking neighbors` 命令还未实现
- `server ps` 命令还未实现
- 本地开发环境可能没有认证库，CLI 的用户相关命令会报错

---

## 七、相关文档

- `README.md` - 项目总览
- `backend/README-ranking-cli.md` - CLI 详细说明
- `backend/main.py` - 后端代码（有注释）

---

如果你是 AI Agent，读完这个应该能在 1 分钟内理解这个项目在干嘛。
