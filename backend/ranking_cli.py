#!/usr/bin/env python3
"""ranking-cli: 易惠达门店排行系统命令行工具（首版）"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Any

DEFAULT_AUTH_CANDIDATES = [
    os.environ.get("RANKING_AUTH_DB"),
    os.path.expanduser("~/ranking_auth.db"),
    os.path.expanduser("~/qnh-data/ranking_auth.db"),
    os.path.join(os.path.dirname(__file__), "ranking_auth.db"),
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "ranking_auth.db"),
]
DEFAULT_QNH_CANDIDATES = [
    os.environ.get("RANKING_QNH_DB"),
    os.path.expanduser("~/qnh-data/qnh.db"),
    os.path.join(os.path.dirname(__file__), "qnh.db"),
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "qnh.db"),
]


def first_existing_path(candidates: list[str | None], fallback: str) -> str:
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return fallback


def get_auth_db_path() -> str:
    return first_existing_path(DEFAULT_AUTH_CANDIDATES, os.path.expanduser("~/ranking_auth.db"))


def get_qnh_db_path() -> str:
    return first_existing_path(DEFAULT_QNH_CANDIDATES, os.path.expanduser("~/qnh-data/qnh.db"))


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def port_is_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def require_db(path: str, label: str) -> None:
    if not os.path.exists(path):
        raise SystemExit(f"{label} 不存在: {path}")


def connect_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_latest_date() -> str | None:
    qnh_db = get_qnh_db_path()
    if not os.path.exists(qnh_db):
        return None
    conn = connect_db(qnh_db)
    try:
        row = conn.execute(
            "SELECT MAX(date) AS latest_date FROM store_daily_full WHERE valid_orders > 0"
        ).fetchone()
        return row["latest_date"] if row else None
    finally:
        conn.close()


def get_available_dates(limit: int = 30) -> list[str]:
    qnh_db = get_qnh_db_path()
    require_db(qnh_db, "业务数据库")
    conn = connect_db(qnh_db)
    try:
        rows = conn.execute(
            "SELECT DISTINCT date FROM store_daily_full WHERE valid_orders > 0 ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [row["date"] for row in rows]
    finally:
        conn.close()


def query_rankings(date: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    qnh_db = get_qnh_db_path()
    require_db(qnh_db, "业务数据库")
    conn = connect_db(qnh_db)
    try:
        if not date:
            row = conn.execute(
                "SELECT MAX(date) AS latest_date FROM store_daily_full WHERE valid_orders > 0"
            ).fetchone()
            date = row["latest_date"] if row else None
        if not date:
            raise SystemExit("未找到可用排行日期")

        prev = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

        today_rows = conn.execute(
            """
            SELECT
                store_name,
                SUM(valid_orders) AS valid_orders,
                SUM(sales_revenue) AS sales_revenue,
                SUM(refund_orders) AS refund_orders,
                SUM(new_customers) AS new_customers,
                SUM(old_customers) AS old_customers,
                SUM(merchant_discount) AS discount
            FROM store_daily_full
            WHERE date = ? AND valid_orders > 0
            GROUP BY store_name
            ORDER BY SUM(valid_orders) DESC, store_name ASC
            """,
            (date,),
        ).fetchall()

        prev_rows = conn.execute(
            """
            SELECT store_name
            FROM store_daily_full
            WHERE date = ? AND valid_orders > 0
            GROUP BY store_name
            ORDER BY SUM(valid_orders) DESC, store_name ASC
            """,
            (prev,),
        ).fetchall()
        prev_rank = {row["store_name"]: idx + 1 for idx, row in enumerate(prev_rows)}

        rankings: list[dict[str, Any]] = []
        for idx, row in enumerate(today_rows, start=1):
            orders = int(row["valid_orders"] or 0)
            revenue = round(float(row["sales_revenue"] or 0), 2)
            rankings.append(
                {
                    "rank": idx,
                    "store_name": row["store_name"],
                    "valid_orders": orders,
                    "sales_revenue": revenue,
                    "avg_price": round(revenue / orders, 1) if orders else 0,
                    "refund_orders": int(row["refund_orders"] or 0),
                    "new_customers": int(row["new_customers"] or 0),
                    "old_customers": int(row["old_customers"] or 0),
                    "discount": round(float(row["discount"] or 0), 2),
                    "rank_change_vs_prev_day": prev_rank.get(row["store_name"], idx) - idx,
                }
            )

        return date, rankings
    finally:
        conn.close()


def parse_store_permissions(raw: str | None) -> list[str]:
    perms_raw = raw or "[]"
    try:
        parsed = json.loads(perms_raw)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def get_user_permissions(username: str) -> dict[str, Any]:
    auth_db = get_auth_db_path()
    require_db(auth_db, "认证数据库")
    conn = connect_db(auth_db)
    try:
        row = conn.execute(
            """
            SELECT username, full_name, is_admin, is_active, store_permissions, created_at, last_login
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
        if not row:
            raise SystemExit(f"用户不存在: {username}")

        store_permissions = parse_store_permissions(row["store_permissions"])

        return {
            "username": row["username"],
            "full_name": row["full_name"],
            "is_admin": bool(row["is_admin"]),
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"],
            "last_login": row["last_login"],
            "store_permissions": store_permissions,
            "effective_access": "all" if (bool(row["is_admin"]) or not store_permissions) else "limited",
        }
    finally:
        conn.close()


def list_users() -> list[dict[str, Any]]:
    auth_db = get_auth_db_path()
    require_db(auth_db, "认证数据库")
    conn = connect_db(auth_db)
    try:
        rows = conn.execute(
            """
            SELECT username, full_name, is_admin, is_active, store_permissions, created_at, last_login
            FROM users
            ORDER BY datetime(created_at) DESC, username ASC
            """
        ).fetchall()
        return [
            {
                "username": row["username"],
                "full_name": row["full_name"],
                "is_admin": bool(row["is_admin"]),
                "is_active": bool(row["is_active"]),
                "created_at": row["created_at"],
                "last_login": row["last_login"],
                "store_permissions_count": len(parse_store_permissions(row["store_permissions"])),
                "effective_access": "all"
                if (bool(row["is_admin"]) or not parse_store_permissions(row["store_permissions"]))
                else "limited",
            }
            for row in rows
        ]
    finally:
        conn.close()


def user_can_view_store(username: str, store_name: str) -> dict[str, Any]:
    user = get_user_permissions(username)
    allowed = user["is_admin"] or not user["store_permissions"] or store_name in user["store_permissions"]
    reason = (
        "管理员可查看全部门店"
        if user["is_admin"]
        else "空权限列表，当前逻辑等同全部可见"
        if not user["store_permissions"]
        else "门店在授权列表内"
        if allowed
        else "门店不在授权列表内"
    )
    return {
        "username": user["username"],
        "store_name": store_name,
        "can_view": allowed,
        "reason": reason,
        "effective_access": user["effective_access"],
    }


def get_db_summary() -> dict[str, Any]:
    qnh_db = get_qnh_db_path()
    auth_db = get_auth_db_path()

    summary: dict[str, Any] = {
        "qnh_db": {"path": qnh_db, "exists": os.path.exists(qnh_db)},
        "auth_db": {"path": auth_db, "exists": os.path.exists(auth_db)},
        "latest_date": None,
        "store_count": None,
        "row_count": None,
        "user_count": None,
        "invite_card_count": None,
    }

    if os.path.exists(qnh_db):
        conn = connect_db(qnh_db)
        try:
            row = conn.execute(
                "SELECT MAX(date) AS latest_date, COUNT(*) AS row_count, COUNT(DISTINCT store_name) AS store_count FROM store_daily_full"
            ).fetchone()
            summary["latest_date"] = row["latest_date"]
            summary["row_count"] = int(row["row_count"] or 0)
            summary["store_count"] = int(row["store_count"] or 0)
        finally:
            conn.close()

    if os.path.exists(auth_db):
        conn = connect_db(auth_db)
        try:
            row = conn.execute(
                "SELECT (SELECT COUNT(*) FROM users) AS user_count, (SELECT COUNT(*) FROM invite_cards) AS invite_card_count"
            ).fetchone()
            summary["user_count"] = int(row["user_count"] or 0)
            summary["invite_card_count"] = int(row["invite_card_count"] or 0)
        finally:
            conn.close()

    return summary


def get_store_daily_row_count() -> int:
    qnh_db = get_qnh_db_path()
    require_db(qnh_db, "业务数据库")
    conn = connect_db(qnh_db)
    try:
        row = conn.execute("SELECT COUNT(*) AS row_count FROM store_daily_full").fetchone()
        return int(row["row_count"] or 0)
    finally:
        conn.close()


def summarize_qnh_db(path: str) -> dict[str, Any]:
    result = {"path": path, "exists": os.path.exists(path), "latest_date": None, "row_count": None}
    if not os.path.exists(path):
        return result
    conn = connect_db(path)
    try:
        row = conn.execute(
            "SELECT MAX(date) AS latest_date, COUNT(*) AS row_count FROM store_daily_full"
        ).fetchone()
        result["latest_date"] = row["latest_date"]
        result["row_count"] = int(row["row_count"] or 0)
        return result
    finally:
        conn.close()


def cmd_health(args: argparse.Namespace) -> int:
    auth_db = get_auth_db_path()
    qnh_db = get_qnh_db_path()
    latest_date = get_latest_date()
    port_8899 = port_is_listening(8899)
    port_8898 = port_is_listening(8898)

    data = {
        "ok": os.path.exists(auth_db) and os.path.exists(qnh_db) and port_8899,
        "auth_db": {"path": auth_db, "exists": os.path.exists(auth_db)},
        "qnh_db": {"path": qnh_db, "exists": os.path.exists(qnh_db)},
        "ports": {"8899": port_8899, "8898": port_8898},
        "latest_date": latest_date,
        "issues": [],
    }

    if not data["auth_db"]["exists"]:
        data["issues"].append("认证数据库不存在")
    if not data["qnh_db"]["exists"]:
        data["issues"].append("业务数据库不存在")
    if not port_8899:
        data["issues"].append("8899 未监听（后端可能没启动或跑错端口）")
    if port_8898:
        data["issues"].append("8898 正在监听（注意是否误把后端跑到了 8898）")
    if not latest_date:
        data["issues"].append("未找到可用排行日期")

    if args.json:
        print_json(data)
        return 0

    print("# ranking-cli health")
    print(f"认证库: {'存在' if data['auth_db']['exists'] else '缺失'}  {data['auth_db']['path']}")
    print(f"业务库: {'存在' if data['qnh_db']['exists'] else '缺失'}  {data['qnh_db']['path']}")
    print(f"端口 8899: {'监听中' if port_8899 else '未监听'}")
    print(f"端口 8898: {'监听中' if port_8898 else '未监听'}")
    print(f"最新排行日期: {latest_date or '-'}")
    if data["issues"]:
        print("\n问题:")
        for item in data["issues"]:
            print(f"- {item}")
    else:
        print("\n状态: 正常")
    return 0


def cmd_server_ports(args: argparse.Namespace) -> int:
    data = {
        "ports": [
            {"port": 8899, "listening": port_is_listening(8899)},
            {"port": 8898, "listening": port_is_listening(8898)},
        ]
    }

    if args.json:
        print_json(data)
        return 0

    print("# ranking-cli server ports")
    for item in data["ports"]:
        print(f"{item['port']}: {'监听中' if item['listening'] else '未监听'}")
    return 0


def cmd_dates_list(args: argparse.Namespace) -> int:
    dates = get_available_dates(limit=args.limit)
    data = {"limit": args.limit, "count": len(dates), "dates": dates}

    if args.json:
        print_json(data)
        return 0

    print("# ranking-cli dates list")
    if not dates:
        print("没有可用日期")
        return 0
    for item in dates:
        print(item)
    return 0


def format_rank_row(row: dict[str, Any]) -> str:
    return (
        f"#{row['rank']:>2}  {row['store_name']}"
        f" | 单量 {row['valid_orders']}"
        f" | 营业额 {row['sales_revenue']:.2f}"
        f" | 客单价 {row['avg_price']:.1f}"
        f" | 退单 {row['refund_orders']}"
        f" | 新客 {row['new_customers']}"
        f" | 老客 {row['old_customers']}"
        f" | 补贴/折扣 {row['discount']:.2f}"
        f" | 较昨日名次变化 {row['rank_change_vs_prev_day']:+d}"
    )


def cmd_ranking_show(args: argparse.Namespace) -> int:
    date, rows = query_rankings(args.date)

    if args.store:
        rows = [row for row in rows if row["store_name"] == args.store]
        if not rows:
            raise SystemExit(f"日期 {date} 未找到门店: {args.store}")
    elif args.limit:
        rows = rows[: args.limit]

    data = {
        "date": date,
        "store": args.store,
        "count": len(rows),
        "rows": rows,
    }

    if args.json:
        print_json(data)
        return 0

    print(f"# ranking-cli ranking show ({date})")
    if not rows:
        print("没有数据")
        return 0

    if args.store:
        row = rows[0]
        print(f"门店: {row['store_name']}")
        print(f"排名: {row['rank']}")
        print(f"有效订单: {row['valid_orders']}")
        print(f"营业额: {row['sales_revenue']:.2f}")
        print(f"客单价: {row['avg_price']:.1f}")
        print(f"退单: {row['refund_orders']}")
        print(f"新客: {row['new_customers']}")
        print(f"老客: {row['old_customers']}")
        print(f"补贴/折扣: {row['discount']:.2f}")
        print(f"较昨日名次变化: {row['rank_change_vs_prev_day']:+d}")
        return 0

    for row in rows:
        print(format_rank_row(row))
    return 0


def cmd_user_perms(args: argparse.Namespace) -> int:
    data = get_user_permissions(args.username)

    if args.json:
        print_json(data)
        return 0

    print("# ranking-cli user perms")
    print(f"用户名: {data['username']}")
    print(f"姓名: {data['full_name'] or '-'}")
    print(f"管理员: {'是' if data['is_admin'] else '否'}")
    print(f"状态: {'启用' if data['is_active'] else '禁用'}")
    print(f"创建时间: {data['created_at'] or '-'}")
    print(f"最近登录: {data['last_login'] or '-'}")
    print(f"有效访问范围: {'全部门店' if data['effective_access'] == 'all' else '有限门店'}")
    print("门店权限:")
    perms = data["store_permissions"]
    if perms:
        for store in perms:
            print(f"- {store}")
    else:
        print("- []（空权限，当前逻辑等同全部可见）")
    return 0


def cmd_user_list(args: argparse.Namespace) -> int:
    users = list_users()
    data = {"count": len(users), "users": users}

    if args.json:
        print_json(data)
        return 0

    print("# ranking-cli user list")
    if not users:
        print("没有用户")
        return 0
    for user in users:
        access_text = (
            "全部门店"
            if user["effective_access"] == "all"
            else f"限 {user['store_permissions_count']} 家"
        )
        print(
            f"{user['username']}"
            f" | 姓名 {user['full_name'] or '-'}"
            f" | {'管理员' if user['is_admin'] else '普通用户'}"
            f" | {'启用' if user['is_active'] else '禁用'}"
            f" | 访问 {access_text}"
            f" | 最近登录 {user['last_login'] or '-'}"
        )
    return 0


def cmd_user_can_view(args: argparse.Namespace) -> int:
    data = user_can_view_store(args.username, args.store)

    if args.json:
        print_json(data)
        return 0

    print("# ranking-cli user can-view")
    print(f"用户名: {data['username']}")
    print(f"门店: {data['store_name']}")
    print(f"结果: {'可查看' if data['can_view'] else '不可查看'}")
    print(f"原因: {data['reason']}")
    return 0


def cmd_db_latest_date(args: argparse.Namespace) -> int:
    data = {"path": get_qnh_db_path(), "latest_date": get_latest_date()}
    if args.json:
        print_json(data)
        return 0

    print("# ranking-cli db latest-date")
    print(data["latest_date"] or "-")
    return 0


def cmd_db_rowcount(args: argparse.Namespace) -> int:
    data = {"path": get_qnh_db_path(), "row_count": get_store_daily_row_count()}
    if args.json:
        print_json(data)
        return 0

    print("# ranking-cli db rowcount")
    print(data["row_count"])
    return 0


def cmd_db_summary(args: argparse.Namespace) -> int:
    data = get_db_summary()
    if args.json:
        print_json(data)
        return 0

    print("# ranking-cli db summary")
    print(f"业务库: {'存在' if data['qnh_db']['exists'] else '缺失'}  {data['qnh_db']['path']}")
    print(f"认证库: {'存在' if data['auth_db']['exists'] else '缺失'}  {data['auth_db']['path']}")
    print(f"最新日期: {data['latest_date'] or '-'}")
    print(f"业务表总行数: {data['row_count'] if data['row_count'] is not None else '-'}")
    print(f"门店数: {data['store_count'] if data['store_count'] is not None else '-'}")
    print(f"用户数: {data['user_count'] if data['user_count'] is not None else '-'}")
    print(f"邀请码数: {data['invite_card_count'] if data['invite_card_count'] is not None else '-'}")
    return 0


def cmd_db_check_sync(args: argparse.Namespace) -> int:
    local_summary = summarize_qnh_db(get_qnh_db_path())
    compare_summary = summarize_qnh_db(args.compare_path) if args.compare_path else None

    data = {
        "local": local_summary,
        "compare": compare_summary,
        "in_sync": None,
        "checks": [],
    }

    if compare_summary:
        same_date = local_summary["latest_date"] == compare_summary["latest_date"]
        same_rows = local_summary["row_count"] == compare_summary["row_count"]
        data["checks"] = [
            {"name": "latest_date", "same": same_date, "local": local_summary["latest_date"], "compare": compare_summary["latest_date"]},
            {"name": "row_count", "same": same_rows, "local": local_summary["row_count"], "compare": compare_summary["row_count"]},
        ]
        data["in_sync"] = all(item["same"] for item in data["checks"])

    if args.json:
        print_json(data)
        return 0

    print("# ranking-cli db check-sync")
    print(f"本地业务库: {local_summary['path']}")
    print(f"- latest_date: {local_summary['latest_date'] or '-'}")
    print(f"- row_count: {local_summary['row_count'] if local_summary['row_count'] is not None else '-'}")
    if not compare_summary:
        print("未提供对比库路径；当前只输出本地业务库摘要。")
        print("提示：排行系统真正同步的是 qnh.db，不是 data.json。")
        return 0

    print(f"对比业务库: {compare_summary['path']}")
    print(f"- latest_date: {compare_summary['latest_date'] or '-'}")
    print(f"- row_count: {compare_summary['row_count'] if compare_summary['row_count'] is not None else '-'}")
    print(f"结论: {'一致' if data['in_sync'] else '不一致'}")
    for item in data['checks']:
        print(f"- {item['name']}: {'一致' if item['same'] else '不一致'}（本地={item['local']} / 对比={item['compare']}）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ranking-cli",
        description="易惠达门店排行系统命令行工具（首版）",
    )
    subparsers = parser.add_subparsers(dest="command")

    p_health = subparsers.add_parser("health", help="检查排行系统关键状态")
    p_health.add_argument("--json", action="store_true", help="输出 JSON")
    p_health.set_defaults(func=cmd_health)

    p_server = subparsers.add_parser("server", help="服务相关命令")
    server_sub = p_server.add_subparsers(dest="server_command")
    p_server_ports = server_sub.add_parser("ports", help="查看 8899/8898 监听状态")
    p_server_ports.add_argument("--json", action="store_true", help="输出 JSON")
    p_server_ports.set_defaults(func=cmd_server_ports)

    p_dates = subparsers.add_parser("dates", help="日期相关命令")
    dates_sub = p_dates.add_subparsers(dest="dates_command")
    p_dates_list = dates_sub.add_parser("list", help="列出可用排行日期")
    p_dates_list.add_argument("--limit", type=int, default=30, help="最多返回多少个日期，默认 30")
    p_dates_list.add_argument("--json", action="store_true", help="输出 JSON")
    p_dates_list.set_defaults(func=cmd_dates_list)

    p_ranking = subparsers.add_parser("ranking", help="排行数据查询")
    ranking_sub = p_ranking.add_subparsers(dest="ranking_command")
    p_ranking_show = ranking_sub.add_parser("show", help="查看某日排行或某门店排名")
    p_ranking_show.add_argument("--date", help="指定日期，格式 YYYY-MM-DD；不传则取最新")
    p_ranking_show.add_argument("--limit", type=int, default=20, help="返回前 N 条，默认 20")
    p_ranking_show.add_argument("--store", help="仅查看指定门店（仍按全量排名计算名次）")
    p_ranking_show.add_argument("--json", action="store_true", help="输出 JSON")
    p_ranking_show.set_defaults(func=cmd_ranking_show)

    p_user = subparsers.add_parser("user", help="用户和权限查询")
    user_sub = p_user.add_subparsers(dest="user_command")
    p_user_perms = user_sub.add_parser("perms", help="查看用户门店权限")
    p_user_perms.add_argument("--username", required=True, help="用户名")
    p_user_perms.add_argument("--json", action="store_true", help="输出 JSON")
    p_user_perms.set_defaults(func=cmd_user_perms)

    p_user_list = user_sub.add_parser("list", help="列出用户")
    p_user_list.add_argument("--json", action="store_true", help="输出 JSON")
    p_user_list.set_defaults(func=cmd_user_list)

    p_user_can_view = user_sub.add_parser("can-view", help="检查用户是否可查看某门店")
    p_user_can_view.add_argument("--username", required=True, help="用户名")
    p_user_can_view.add_argument("--store", required=True, help="门店名")
    p_user_can_view.add_argument("--json", action="store_true", help="输出 JSON")
    p_user_can_view.set_defaults(func=cmd_user_can_view)

    p_db = subparsers.add_parser("db", help="数据库摘要与同步检查")
    db_sub = p_db.add_subparsers(dest="db_command")

    p_db_latest_date = db_sub.add_parser("latest-date", help="查看业务库最新日期")
    p_db_latest_date.add_argument("--json", action="store_true", help="输出 JSON")
    p_db_latest_date.set_defaults(func=cmd_db_latest_date)

    p_db_rowcount = db_sub.add_parser("rowcount", help="查看 store_daily_full 总行数")
    p_db_rowcount.add_argument("--json", action="store_true", help="输出 JSON")
    p_db_rowcount.set_defaults(func=cmd_db_rowcount)

    p_db_summary = db_sub.add_parser("summary", help="查看业务库/认证库摘要")
    p_db_summary.add_argument("--json", action="store_true", help="输出 JSON")
    p_db_summary.set_defaults(func=cmd_db_summary)

    p_db_check_sync = db_sub.add_parser("check-sync", help="检查 qnh.db 同步状态")
    p_db_check_sync.add_argument("--compare-path", help="对比另一份 qnh.db 路径")
    p_db_check_sync.add_argument("--json", action="store_true", help="输出 JSON")
    p_db_check_sync.set_defaults(func=cmd_db_check_sync)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if not func:
        parser.print_help()
        return 1
    return int(func(args) or 0)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        raise SystemExit(130)
