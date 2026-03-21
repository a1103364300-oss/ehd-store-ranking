# ranking-cli

易惠达门店排行系统命令行工具（首版）。

## 位置

```bash
python3 backend/ranking_cli.py ...
```

默认会自动探测数据库路径：

- 认证库候选：`$RANKING_AUTH_DB` → `~/ranking_auth.db` → `~/qnh-data/ranking_auth.db` → 项目目录附近
- 业务库候选：`$RANKING_QNH_DB` → `~/qnh-data/qnh.db` → 项目目录附近

也可以手动指定：

```bash
RANKING_AUTH_DB=/path/to/ranking_auth.db RANKING_QNH_DB=/path/to/qnh.db python3 backend/ranking_cli.py health
```

## 已支持命令

### 1. 健康检查

```bash
python3 backend/ranking_cli.py health
python3 backend/ranking_cli.py health --json
```

检查：
- 认证库是否存在
- 业务库是否存在
- 8899 是否监听
- 8898 是否监听
- 最新排行日期

### 2. 端口状态

```bash
python3 backend/ranking_cli.py server ports
python3 backend/ranking_cli.py server ports --json
```

### 3. 可用日期

```bash
python3 backend/ranking_cli.py dates list
python3 backend/ranking_cli.py dates list --limit 10
python3 backend/ranking_cli.py dates list --json
```

### 4. 排行查询

```bash
python3 backend/ranking_cli.py ranking show
python3 backend/ranking_cli.py ranking show --date 2026-03-21
python3 backend/ranking_cli.py ranking show --date 2026-03-21 --limit 10
python3 backend/ranking_cli.py ranking show --date 2026-03-21 --store "港城路店"
python3 backend/ranking_cli.py ranking show --date 2026-03-21 --json
```

返回字段：
- `rank`
- `store_name`
- `valid_orders`
- `sales_revenue`
- `avg_price`
- `refund_orders`
- `new_customers`
- `old_customers`
- `discount`
- `rank_change_vs_prev_day`

### 5. 用户权限查询

```bash
python3 backend/ranking_cli.py user perms --username admin
python3 backend/ranking_cli.py user perms --username admin --json
python3 backend/ranking_cli.py user list
python3 backend/ranking_cli.py user can-view --username aron --store "世纪华联超市（长宁中心店）"
```

### 6. 数据库摘要 / 同步检查

```bash
python3 backend/ranking_cli.py db latest-date
python3 backend/ranking_cli.py db rowcount
python3 backend/ranking_cli.py db summary
python3 backend/ranking_cli.py db check-sync
python3 backend/ranking_cli.py db check-sync --compare-path /path/to/qnh.db
python3 backend/ranking_cli.py db summary --json
```

说明：
- `db check-sync` 默认先输出当前业务库摘要
- 如果传 `--compare-path`，会比较两份 `qnh.db` 的 `latest_date` 和 `row_count`
- 这里固化的是：**排行系统真正同步的是 `qnh.db`，不是 `data.json`**

## 当前边界

这版先做只读查询，不碰重启、改权限、改数据之类的写操作。

后续可继续加：
- `server ps`
- `ranking neighbors`
- `export ranking`
- `user show`
