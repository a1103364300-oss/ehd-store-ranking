#!/usr/bin/env python3
"""
门店排行榜每日自动更新脚本
生成 data.json 并推送到服务器

注意：
- 不再自动同步 index.html / store.html / 其他前端页面
- 原因：本地项目中存在旧版静态页与新版前端的双轨文件，自动推页面容易误把服务器上的新版页面覆盖回旧版
- 当前默认只同步 data.json，前端页面如需发布应走明确的人为发布流程
"""
import sqlite3, json, os, subprocess
from datetime import datetime, timedelta

DB = os.path.expanduser('~/qnh-data/qnh.db')
DIST = '/Users/macos/clawd/projects/store-ranking/dist/ranking'
SERVER = 'ubuntu@43.128.147.27'
KEY = os.path.expanduser('~/Downloads/clawdbot.pem')
REMOTE_DIR = '/home/ubuntu/nofx-Metroll/dist/ranking'

os.makedirs(DIST, exist_ok=True)

# ── 拉数据 ──────────────────────────────────────────
conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("SELECT DISTINCT date FROM store_daily_full WHERE valid_orders > 0 ORDER BY date DESC LIMIT 30")
dates = [r[0] for r in cur.fetchall()]

all_data = {}
for date in dates:
    prev = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    cur.execute('''
        SELECT store_name, SUM(valid_orders), SUM(sales_revenue), SUM(refund_orders),
               SUM(new_customers), SUM(old_customers), SUM(merchant_discount), SUM(platform_subsidy)
        FROM store_daily_full WHERE date = ? AND valid_orders > 0
        GROUP BY store_name ORDER BY SUM(valid_orders) DESC
    ''', (date,))
    today_rows = cur.fetchall()
    cur.execute('''
        SELECT store_name FROM store_daily_full WHERE date = ? AND valid_orders > 0
        GROUP BY store_name ORDER BY SUM(valid_orders) DESC
    ''', (prev,))
    prev_rank = {r[0]: i+1 for i, r in enumerate(cur.fetchall())}
    cur.execute('SELECT SUM(valid_orders),SUM(sales_revenue),SUM(new_customers),SUM(old_customers),SUM(refund_orders) FROM store_daily_full WHERE date=?', (date,))
    s = cur.fetchone()
    total_orders = int(s[0] or 0)
    total_revenue = round(float(s[1] or 0), 2)
    stores = []
    for i, row in enumerate(today_rows):
        name, orders, revenue, refund, nc, oc, disc, platform = row
        orders = int(orders or 0)
        revenue = round(float(revenue or 0), 2)
        stores.append({
            'rank': i+1,
            'rankChange': prev_rank.get(name, i+1) - (i+1),
            'name': name,
            'orders': orders,
            'revenue': revenue,
            'avgPrice': round(revenue/orders, 1) if orders else 0,
            'refundOrders': int(refund or 0),
            'newCustomers': int(nc or 0),
            'oldCustomers': int(oc or 0),
            'discount': round(float(disc or 0), 2),
        })
    all_data[date] = {
        'date': date,
        'totalOrders': total_orders,
        'totalRevenue': total_revenue,
        'totalNew': int(s[2] or 0),
        'totalOld': int(s[3] or 0),
        'totalRefund': int(s[4] or 0),
        'avgPrice': round(total_revenue/total_orders, 2) if total_orders else 0,
        'stores': stores
    }

conn.close()

with open(f'{DIST}/data.json', 'w', encoding='utf-8') as f:
    json.dump({'dates': dates, 'data': all_data}, f, ensure_ascii=False)
print(f"✅ data.json 生成：{len(dates)} 天")

# ── 推送到服务器 ──────────────────────────────────────
# 只同步 data.json，避免用本地旧版前端页面覆盖服务器上可能更新过的 index/store 页面
for fname in ['data.json']:
    src = f'{DIST}/{fname}'
    if not os.path.exists(src):
        print(f"⚠️  {fname} 不存在，跳过")
        continue
    r = subprocess.run([
        'scp', '-i', KEY, '-o', 'StrictHostKeyChecking=no',
        src, f'{SERVER}:{REMOTE_DIR}/{fname}'
    ], capture_output=True)
    if r.returncode == 0:
        # 修复权限
        subprocess.run(['ssh', '-i', KEY, '-o', 'StrictHostKeyChecking=no',
                        SERVER, f'chmod 644 {REMOTE_DIR}/{fname}'], capture_output=True)
        print(f"✅ {fname} 已推送")
    else:
        print(f"❌ {fname} 推送失败: {r.stderr.decode()}")

print(f"🎉 完成！{datetime.now().strftime('%Y-%m-%d %H:%M')}")
