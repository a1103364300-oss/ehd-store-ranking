#!/usr/bin/env python3
"""
易惠达门店排行榜 - 后端 API（含利润分析模块）
新增：/api/profit/* 系列接口，权限控制为管理员或有权限的门店
"""
import sqlite3, os, secrets, string, hashlib, json
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext

DB_PATH = os.path.expanduser('~/ranking_auth.db')
QNH_DB = os.path.expanduser('~/qnh-data/qnh.db')
SECRET_KEY = "ehd-ranking-secret-2026-xK9mP2nQ"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI(title="EHD Ranking API")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ==================== 初始化数据库 ====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            is_admin INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            store_permissions TEXT DEFAULT '[]',
            profit_permission INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            last_login TEXT
        );
        CREATE TABLE IF NOT EXISTS invite_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_no TEXT UNIQUE NOT NULL,
            is_used INTEGER DEFAULT 0,
            used_by TEXT,
            used_at TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            ip TEXT,
            success INTEGER,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
    ''')
    # 添加 profit_permission 列（如果不存在）
    try:
        c.execute("ALTER TABLE users ADD COLUMN profit_permission INTEGER DEFAULT 0")
    except:
        pass
    c.execute("SELECT id FROM users WHERE username='admin'")
    if not c.fetchone():
        ph = pwd_context.hash("Admin2026!")
        c.execute("INSERT INTO users(username,password_hash,full_name,is_admin,profit_permission,store_permissions) VALUES(?,?,?,1,1,'[]')",
                  ('admin', ph, '超级管理员'))
    conn.commit()
    conn.close()

init_db()

# ==================== JWT 工具 ====================
def create_token(data: dict):
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode({**data, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token无效或已过期")

def get_current_user(username: str = Depends(verify_token)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if not user or not user['is_active']:
        raise HTTPException(status_code=401, detail="账号不存在或已被封禁")
    return dict(user)

def get_user_store_permissions(user: dict) -> list:
    """解析用户的门店权限（数据库存储为 JSON 字符串）"""
    perms_raw = user.get('store_permissions', '[]')
    if isinstance(perms_raw, str):
        return json.loads(perms_raw)
    return perms_raw if perms_raw else []

def require_admin(user=Depends(get_current_user)):
    if not user['is_admin']:
        raise HTTPException(403, "需要管理员权限")
    return user

def require_profit_permission(user=Depends(get_current_user)):
    """要求利润分析权限：管理员或有 profit_permission 标记"""
    if not user['is_admin'] and not user.get('profit_permission'):
        raise HTTPException(403, "无利润分析权限，请联系管理员开通")
    return user

# ==================== 请求模型 ====================
class LoginReq(BaseModel):
    username: str
    password: str

class RegisterReq(BaseModel):
    username: str
    password: str
    full_name: str
    invite_card: str

class UpdateUserReq(BaseModel):
    is_active: Optional[int] = None
    store_permissions: Optional[List[str]] = None
    full_name: Optional[str] = None
    profit_permission: Optional[int] = None

class CreateInviteReq(BaseModel):
    count: int = 1
    note: str = ""

# ==================== 登录注册 ====================
@app.post("/api/login")
def login(req: LoginReq):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    user = conn.execute("SELECT * FROM users WHERE username=?", (req.username,)).fetchone()
    if not user or not pwd_context.verify(req.password, user['password_hash']):
        conn.close()
        raise HTTPException(401, "账号或密码错误")
    if not user['is_active']:
        conn.close()
        raise HTTPException(403, "账号已被封禁，请联系管理员")
    conn.execute("UPDATE users SET last_login=datetime('now','localtime') WHERE username=?", (req.username,))
    conn.commit()
    conn.close()
    token = create_token({"sub": req.username, "is_admin": user['is_admin']})
    return {
        "token": token,
        "is_admin": user['is_admin'],
        "full_name": user['full_name'],
        "store_permissions": json.loads(user['store_permissions'] or '[]'),
        "profit_permission": user['profit_permission'] if 'profit_permission' in user.keys() else 0
    }

@app.get("/api/me")
def me(user=Depends(get_current_user)):
    return {
        "username": user['username'],
        "full_name": user['full_name'],
        "is_admin": user['is_admin'],
        "store_permissions": json.loads(user['store_permissions'] or '[]'),
        "profit_permission": user['profit_permission'] if 'profit_permission' in user.keys() else 0
    }

@app.post("/api/register")
def register(req: RegisterReq):
    if len(req.password) < 6:
        raise HTTPException(400, "密码至少6位")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    card = conn.execute("SELECT * FROM invite_cards WHERE card_no=? AND is_used=0", (req.invite_card,)).fetchone()
    if not card:
        conn.close()
        raise HTTPException(400, "邀请码无效或已使用")
    existing = conn.execute("SELECT id FROM users WHERE username=?", (req.username,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(400, "该账号已存在")
    ph = pwd_context.hash(req.password)
    conn.execute("INSERT INTO users(username,password_hash,full_name) VALUES(?,?,?)", (req.username, ph, req.full_name))
    conn.execute("UPDATE invite_cards SET is_used=1, used_by=?, used_at=datetime('now','localtime') WHERE card_no=?", (req.username, req.invite_card))
    conn.commit()
    conn.close()
    return {"ok": True}

# ==================== 排行榜 API ====================
@app.get("/api/ranking")
def get_ranking(date: str = None, user=Depends(get_current_user)):
    conn = sqlite3.connect(QNH_DB)
    cur = conn.cursor()
    if not date:
        cur.execute("SELECT MAX(date) FROM store_daily_full WHERE valid_orders>0")
        date = cur.fetchone()[0]
    prev = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    perms = json.loads(user['store_permissions'] or '[]') if not user['is_admin'] else []
    is_admin = user['is_admin']
    cur.execute('SELECT store_name, SUM(valid_orders), SUM(sales_revenue), SUM(refund_orders), SUM(new_customers), SUM(old_customers), SUM(merchant_discount), SUM(platform_subsidy) FROM store_daily_full WHERE date=? AND valid_orders>0 GROUP BY store_name ORDER BY SUM(valid_orders) DESC', (date,))
    today_rows = cur.fetchall()
    cur.execute("SELECT store_name FROM store_daily_full WHERE date=? AND valid_orders>0 GROUP BY store_name ORDER BY SUM(valid_orders) DESC", (prev,))
    prev_rank = {r[0]: i+1 for i, r in enumerate(cur.fetchall())}
    cur.execute("SELECT SUM(valid_orders),SUM(sales_revenue),SUM(new_customers),SUM(old_customers),SUM(refund_orders),SUM(merchant_discount),SUM(platform_subsidy) FROM store_daily_full WHERE date=?", (date,))
    s = cur.fetchone()
    total_stores = len(today_rows)
    total_orders = int(s[0] or 0)
    total_revenue = round(float(s[1] or 0), 2)
    all_stores = []
    for i, row in enumerate(today_rows):
        name, orders, revenue, refund, nc, oc, disc, platform = row
        orders = int(orders or 0)
        revenue = round(float(revenue or 0), 2)
        all_stores.append({'rank': i+1, 'rankChange': prev_rank.get(name, i+1) - (i+1), 'name': name, 'orders': orders, 'revenue': revenue, 'avgPrice': round(revenue/orders, 1) if orders else 0, 'refundOrders': int(refund or 0), 'newCustomers': int(nc or 0), 'oldCustomers': int(oc or 0), 'discount': round(float(disc or 0), 2)})
    conn.close()
    has_all_perms = len(perms) >= total_stores and all(st['name'] in perms for st in all_stores)
    if is_admin or has_all_perms:
        stores = all_stores
        neighbors = []
    else:
        stores = [st for st in all_stores if st['name'] in perms]
        neighbors = []
        for st in stores:
            rank = st['rank']
            if rank > 1:
                higher = next((x for x in all_stores if x['rank'] == rank - 1), None)
                if higher and higher not in neighbors:
                    neighbors.append(higher)
            if rank < total_stores:
                lower = next((x for x in all_stores if x['rank'] == rank + 1), None)
                if lower and lower not in neighbors:
                    neighbors.append(lower)
        neighbors.sort(key=lambda x: x['rank'])
    # 计算新客占比、活动力度
    total_merchant_discount = float(s[5] or 0)
    total_platform_subsidy = float(s[6] or 0)
    total_new = int(s[2] or 0)
    total_old = int(s[3] or 0)
    total_customers = total_new + total_old
    new_customer_rate = round(total_new / total_customers * 100, 1) if total_customers > 0 else 0
    merchant_discount_rate = round(total_merchant_discount / total_revenue * 100, 1) if total_revenue > 0 else 0
    platform_subsidy_rate = round(total_platform_subsidy / total_revenue * 100, 1) if total_revenue > 0 else 0

    return {'date': date, 'totalStores': total_stores, 'totalOrders': total_orders, 'totalRevenue': total_revenue, 'avgPrice': round(total_revenue/total_orders, 2) if total_orders else 0, 'totalNew': total_new, 'totalOld': total_old, 'totalRefund': int(s[4] or 0), 'newCustomerRate': new_customer_rate, 'merchantDiscountRate': merchant_discount_rate, 'platformSubsidyRate': platform_subsidy_rate, 'stores': stores, 'neighbors': neighbors, 'hasLimitedPerms': not is_admin and len(perms) > 0 and len(stores) < total_stores}

@app.get("/api/available-dates")
def available_dates(user=Depends(get_current_user)):
    conn = sqlite3.connect(QNH_DB)
    dates = conn.execute("SELECT DISTINCT date FROM store_daily_full WHERE valid_orders>0 ORDER BY date DESC LIMIT 60").fetchall()
    conn.close()
    return {"dates": [d[0] for d in dates]}

@app.get("/api/store-history")
def store_history(name: str, user=Depends(get_current_user)):
    conn = sqlite3.connect(QNH_DB)
    rows = conn.execute('SELECT date, SUM(valid_orders), SUM(sales_revenue), SUM(refund_orders), SUM(new_customers), SUM(old_customers), SUM(merchant_discount) FROM store_daily_full WHERE store_name=? AND valid_orders>0 GROUP BY date ORDER BY date DESC LIMIT 30', (name,)).fetchall()
    history_with_rank = []
    for r in rows:
        date = r[0]
        orders = int(r[1] or 0)
        all_stores = conn.execute('SELECT store_name, SUM(valid_orders) as o FROM store_daily_full WHERE date=? AND valid_orders>0 GROUP BY store_name ORDER BY o DESC', (date,)).fetchall()
        rank = 1
        for i, s in enumerate(all_stores):
            if s[1] > orders:
                rank = i + 2
            elif s[0] == name or s[1] == orders:
                rank = i + 1
                break
        revenue = round(float(r[2] or 0), 2)
        history_with_rank.append({'date': date, 'rank': rank, 'orders': orders, 'revenue': revenue, 'avgPrice': round(revenue/orders, 1) if orders else 0, 'refundOrders': int(r[3] or 0), 'newCustomers': int(r[4] or 0), 'oldCustomers': int(r[5] or 0), 'discount': round(float(r[6] or 0), 2)})
    conn.close()
    return {"name": name, "history": history_with_rank}

@app.get("/api/rank-compare")
def rank_compare(name: str, date: str, user=Depends(get_current_user)):
    conn = sqlite3.connect(QNH_DB)
    cur = conn.cursor()
    cur.execute('SELECT store_name, SUM(valid_orders), SUM(sales_revenue), SUM(refund_orders), SUM(new_customers), SUM(old_customers), SUM(merchant_discount) FROM store_daily_full WHERE date=? AND valid_orders>0 GROUP BY store_name ORDER BY SUM(valid_orders) DESC', (date,))
    rows = cur.fetchall()
    conn.close()
    total_stores = len(rows)
    all_stores = []
    for i, row in enumerate(rows):
        sname, orders, revenue, refund, nc, oc, disc = row
        orders = int(orders or 0)
        revenue = round(float(revenue or 0), 2)
        all_stores.append({'rank': i+1, 'name': sname, 'orders': orders, 'revenue': revenue, 'avgPrice': round(revenue/orders, 1) if orders else 0, 'refundOrders': int(refund or 0), 'newCustomers': int(nc or 0), 'oldCustomers': int(oc or 0), 'discount': round(float(disc or 0), 2)})
    current = next((s for s in all_stores if s['name'] == name), None)
    if not current:
        return {"current": None, "neighbors": [], "totalStores": total_stores}
    neighbors = []
    rank = current['rank']
    if rank > 1:
        higher = next((s for s in all_stores if s['rank'] == rank - 1), None)
        if higher:
            neighbors.append(higher)
    if rank < total_stores:
        lower = next((s for s in all_stores if s['rank'] == rank + 1), None)
        if lower:
            neighbors.append(lower)
    return {"current": current, "neighbors": neighbors, "totalStores": total_stores}

# ==================== 管理员 API ====================
@app.get("/api/admin/users")
def list_users(admin=Depends(require_admin)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    users = conn.execute("SELECT id,username,full_name,is_admin,is_active,store_permissions,profit_permission,created_at,last_login FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    result = []
    for u in users:
        d = dict(u)
        d['store_permissions'] = json.loads(d['store_permissions'] or '[]')
        result.append(d)
    return {"users": result}

@app.patch("/api/admin/users/{username}")
def update_user(username: str, req: UpdateUserReq, admin=Depends(require_admin)):
    if username == 'admin' and req.is_active == 0:
        raise HTTPException(400, "不能封禁超级管理员")
    conn = sqlite3.connect(DB_PATH)
    if req.is_active is not None:
        conn.execute("UPDATE users SET is_active=? WHERE username=?", (req.is_active, username))
    if req.store_permissions is not None:
        conn.execute("UPDATE users SET store_permissions=? WHERE username=?", (json.dumps(req.store_permissions, ensure_ascii=False), username))
    if req.full_name is not None:
        conn.execute("UPDATE users SET full_name=? WHERE username=?", (req.full_name, username))
    if req.profit_permission is not None:
        conn.execute("UPDATE users SET profit_permission=? WHERE username=?", (req.profit_permission, username))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/api/admin/invite-cards")
def list_invite_cards(admin=Depends(require_admin)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cards = conn.execute("SELECT * FROM invite_cards ORDER BY created_at DESC LIMIT 100").fetchall()
    conn.close()
    return {"cards": [dict(c) for c in cards]}

@app.post("/api/admin/invite-cards")
def create_invite_cards(req: CreateInviteReq, admin=Depends(require_admin)):
    conn = sqlite3.connect(DB_PATH)
    cards = []
    for _ in range(req.count):
        card_no = 'EHD-' + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)) + '-' + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
        conn.execute("INSERT INTO invite_cards(card_no, created_by, note) VALUES(?,?,?)", (card_no, admin['username'], req.note))
        cards.append(card_no)
    conn.commit()
    conn.close()
    return {"cards": cards}

@app.get("/api/admin/all-stores")
def get_all_stores(admin=Depends(require_admin)):
    conn = sqlite3.connect(QNH_DB)
    stores = conn.execute("SELECT DISTINCT store_name FROM store_daily_full ORDER BY store_name").fetchall()
    conn.close()
    return {"stores": [s[0] for s in stores]}

# ==================== 利润分析 API ====================
@app.get("/api/profit/overview")
def profit_overview(start: str = Query(...), end: str = Query(...), user=Depends(require_profit_permission)):
    """区间概览数据"""
    conn = sqlite3.connect(QNH_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.execute('''
        select
            count(distinct store_id) as tracked_stores,
            sum(online_gross_profit) as gross,
            sum(operating_profit) as op,
            sum(taobao_promo_cost) as taobao,
            sum(meituan_promo_cost) as meituan,
            sum(daily_cost) as cost,
            sum(case when operating_profit < 0 then 1 else 0 end) as negDays
        from store_operating_profit_daily
        where date between ? and ?
    ''', (start, end))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}

@app.get("/api/profit/daily")
def profit_daily(start: str = Query(...), end: str = Query(...), user=Depends(require_profit_permission)):
    """区间内每日明细"""
    conn = sqlite3.connect(QNH_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        select store_id, store_name, date, online_gross_profit, operating_profit,
               taobao_promo_cost, meituan_promo_cost, daily_cost
        from store_operating_profit_daily
        where date between ? and ?
    ''', (start, end)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/profit/daily-totals")
def profit_daily_totals(start: str = Query(...), end: str = Query(...), user=Depends(require_profit_permission)):
    """区间内每日汇总"""
    conn = sqlite3.connect(QNH_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        select date,
               sum(online_gross_profit) as online_gross_profit,
               sum(operating_profit) as operating_profit,
               sum(daily_cost) as daily_cost
        from store_operating_profit_daily
        where date between ? and ?
        group by date
    ''', (start, end)).fetchall()
    conn.close()
    return {r['date']: dict(r) for r in rows}

@app.get("/api/profit/store-agg")
def profit_store_agg(start: str = Query(...), end: str = Query(...), user=Depends(require_profit_permission)):
    """区间内门店汇总"""
    conn = sqlite3.connect(QNH_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        select store_id, store_name,
               sum(online_gross_profit) as gross,
               sum(operating_profit) as op,
               sum(taobao_promo_cost) as taobao,
               sum(meituan_promo_cost) as meituan,
               sum(daily_cost) as cost,
               sum(case when operating_profit < 0 then 1 else 0 end) as negDays
        from store_operating_profit_daily
        where date between ? and ?
        group by store_id, store_name
    ''', (start, end)).fetchall()
    conn.close()
    return {r['store_id']: dict(r) for r in rows}

@app.get("/api/profit/monthly")
def profit_monthly(user=Depends(require_profit_permission)):
    """月度汇总"""
    conn = sqlite3.connect(QNH_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        select month, store_id, store_name, online_gross_profit, operating_profit,
               days_count, meituan_promo_cost, taobao_promo_cost, daily_cost
        from store_operating_profit_monthly
        order by month, operating_profit desc
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/profit/store-base")
def profit_store_base(user=Depends(require_profit_permission)):
    """门店基础信息（每日成本）"""
    conn = sqlite3.connect(QNH_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        select store_id, store_name, business_mode, region_name, daily_cost
        from store_base_info
        order by daily_cost desc, store_name
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/profit/meta")
def profit_meta(user=Depends(require_profit_permission)):
    """元数据：日期范围、最大值等"""
    conn = sqlite3.connect(QNH_DB)
    min_date = conn.execute("select min(date) from store_operating_profit_daily").fetchone()[0]
    max_date = conn.execute("select max(date) from store_operating_profit_daily").fetchone()[0]
    max_op = conn.execute("select max(abs(operating_profit)) from store_operating_profit_daily").fetchone()[0] or 1
    max_gross = conn.execute("select max(abs(online_gross_profit)) from store_operating_profit_daily").fetchone()[0] or 1
    conn.close()
    return {"minDate": min_date, "maxDate": max_date, "maxOp": max_op, "maxGross": max_gross}



# ==================== 我的利润分析 API ====================

@app.get("/api/profit/my-stores")
def profit_my_stores(user=Depends(get_current_user)):
    """返回用户有权限的门店列表（仅包含有利润数据的门店）"""
    if user['is_admin']:
        conn = sqlite3.connect(QNH_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT DISTINCT store_id, store_name FROM store_operating_profit_daily ORDER BY store_name").fetchall()
        conn.close()
        return {"stores": [dict(r) for r in rows], "is_admin": True}
    
    # 解析 store_permissions（数据库存储为 JSON 字符串）
    perms_raw = user.get('store_permissions', '[]')
    if isinstance(perms_raw, str):
        perms = json.loads(perms_raw)
    else:
        perms = perms_raw if perms_raw else []
    
    if not perms:
        return {"stores": [], "is_admin": False, "message": "无门店权限，请联系管理员开通"}
    
    conn = sqlite3.connect(QNH_DB)
    conn.row_factory = sqlite3.Row
    placeholders = ','.join('?' * len(perms))
    rows = conn.execute(f"SELECT DISTINCT store_id, store_name FROM store_operating_profit_daily WHERE store_name IN ({placeholders})", perms).fetchall()
    conn.close()
    
    stores = [dict(r) for r in rows]
    if not stores:
        return {"stores": [], "is_admin": False, "message": "您的门店暂无利润数据，请稍后再试"}
    
    return {"stores": stores, "is_admin": False}

@app.get("/api/profit/my-overview")
def profit_my_overview(store_name: str = Query(...), month: str = Query(None), user=Depends(get_current_user)):
    """门店月度总览 + 洞察"""
    # 权限检查
    if not user['is_admin']:
        perms = get_user_store_permissions(user)
        if store_name not in perms:
            raise HTTPException(403, "无权查看此门店")
    
    # 默认当月
    if not month:
        month = datetime.now().strftime('%Y-%m')
    
    conn = sqlite3.connect(QNH_DB)
    conn.row_factory = sqlite3.Row
    
    # 当月数据
    cur = conn.execute('''
        SELECT store_id, store_name,
               SUM(online_gross_profit) as gross,
               SUM(operating_profit) as op,
               SUM(taobao_promo_cost) as taobao,
               SUM(meituan_promo_cost) as meituan,
               SUM(daily_cost) as cost,
               SUM(CASE WHEN operating_profit < 0 THEN 1 ELSE 0 END) as neg_days,
               COUNT(*) as days
        FROM store_operating_profit_daily
        WHERE store_name = ? AND date LIKE ?
    ''', (store_name, month + '%')).fetchone()
    
    # 上月数据（用于环比）
    prev_month_dt = datetime.strptime(month, '%Y-%m') - timedelta(days=32)
    prev_month = prev_month_dt.strftime('%Y-%m')
    prev = conn.execute('''
        SELECT SUM(operating_profit) as op, SUM(online_gross_profit) as gross
        FROM store_operating_profit_daily
        WHERE store_name = ? AND date LIKE ?
    ''', (store_name, prev_month + '%')).fetchone()
    
    # 全部门店平均推广占比
    print(f"DEBUG: month={month}, params={(month + '%',)}, len={len((month + '%',))}")
    avg_promo = conn.execute('''
        SELECT AVG(CASE WHEN online_gross_profit > 0 
            THEN (taobao_promo_cost + meituan_promo_cost) * 1.0 / online_gross_profit * 100 ELSE 0 END) as rate
        FROM store_operating_profit_daily
        WHERE date LIKE ?
    ''', (month + '%',)).fetchone()['rate'] or 0
    
    # 获取排名信息
    all_stores = conn.execute('''
        SELECT store_name, SUM(operating_profit) as op
        FROM store_operating_profit_daily
        WHERE date LIKE ?
        GROUP BY store_name
        ORDER BY op DESC
    ''', (month + '%',)).fetchall()
    
    rank = 0
    for i, s in enumerate(all_stores):
        if s['store_name'] == store_name:
            rank = i + 1
            break
    
    conn.close()
    
    op = float(cur['op'] or 0)
    gross = float(cur['gross'] or 0)
    taobao = float(cur['taobao'] or 0)
    meituan = float(cur['meituan'] or 0)
    promo = taobao + meituan
    prev_op = float(prev['op'] or 0)
    prev_gross = float(prev['gross'] or 0)
    
    op_change = ((op - prev_op) / prev_op * 100) if prev_op != 0 else 0
    gross_change = ((gross - prev_gross) / prev_gross * 100) if prev_gross != 0 else 0
    
    return {
        "store": store_name,
        "month": month,
        "profit": round(op, 2),
        "gross": round(gross, 2),
        "taobao": round(taobao, 2),
        "meituan": round(meituan, 2),
        "promo": round(promo, 2),
        "cost": round(float(cur['cost'] or 0), 2),
        "profitRate": round(op / gross * 100, 1) if gross > 0 else 0,
        "promoRate": round(promo / gross * 100, 1) if gross > 0 else 0,
        "avgPromoRate": round(avg_promo, 1),
        "negDays": int(cur['neg_days'] or 0),
        "days": int(cur['days'] or 0),
        "rank": rank,
        "totalStores": len(all_stores),
        "change": {
            "profit": round(op_change, 1),
            "gross": round(gross_change, 1)
        }
    }

@app.get("/api/profit/my-trend")
def profit_my_trend(store_name: str = Query(...), days: int = Query(30), user=Depends(get_current_user)):
    """门店趋势数据"""
    if not user['is_admin']:
        perms = get_user_store_permissions(user)
        if store_name not in perms:
            raise HTTPException(403, "无权查看此门店")
    
    conn = sqlite3.connect(QNH_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        SELECT date, online_gross_profit as gross, operating_profit as op,
               taobao_promo_cost as taobao, meituan_promo_cost as meituan
        FROM store_operating_profit_daily
        WHERE store_name = ?
        ORDER BY date DESC
        LIMIT ?
    ''', (store_name, days)).fetchall()
    conn.close()
    
    return {"trend": [dict(r) for r in reversed(rows)]}

@app.get("/api/profit/my-daily")
def profit_my_daily(store_name: str = Query(...), month: str = Query(None), user=Depends(get_current_user)):
    """门店每日明细"""
    if not user['is_admin']:
        perms = get_user_store_permissions(user)
        if store_name not in perms:
            raise HTTPException(403, "无权查看此门店")
    
    if not month:
        month = datetime.now().strftime('%Y-%m')
    
    conn = sqlite3.connect(QNH_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        SELECT date, online_gross_profit as gross, operating_profit as op,
               taobao_promo_cost as taobao, meituan_promo_cost as meituan, daily_cost as cost
        FROM store_operating_profit_daily
        WHERE store_name = ? AND date LIKE ?
        ORDER BY date DESC
    ''', (store_name, month + '%')).fetchall()
    conn.close()
    
    return {"daily": [dict(r) for r in rows], "month": month}

@app.get("/api/profit/my-compare")
def profit_my_compare(store_name: str = Query(...), month: str = Query(None), user=Depends(get_current_user)):
    """邻居门店对比"""
    if not user['is_admin']:
        perms = get_user_store_permissions(user)
        if store_name not in perms:
            raise HTTPException(403, "无权查看此门店")
    
    if not month:
        month = datetime.now().strftime('%Y-%m')
    
    conn = sqlite3.connect(QNH_DB)
    conn.row_factory = sqlite3.Row
    
    # 获取所有门店排名
    all_stores = conn.execute('''
        SELECT store_name, SUM(operating_profit) as op, SUM(online_gross_profit) as gross
        FROM store_operating_profit_daily
        WHERE date LIKE ?
        GROUP BY store_name
        ORDER BY op DESC
    ''', (month + '%',)).fetchall()
    conn.close()
    
    result = {"current": None, "neighbors": [], "rank": 0, "total": len(all_stores)}
    
    for i, s in enumerate(all_stores):
        if s['store_name'] == store_name:
            result['current'] = {
                "rank": i + 1, 
                "name": s['store_name'], 
                "profit": round(float(s['op'] or 0), 2),
                "gross": round(float(s['gross'] or 0), 2)
            }
            result['rank'] = i + 1
            # 前一名
            if i > 0:
                prev = all_stores[i - 1]
                result['neighbors'].append({
                    "rank": i, 
                    "name": prev['store_name'], 
                    "profit": round(float(prev['op'] or 0), 2),
                    "diff": "higher",
                    "gap": round(float(prev['op'] or 0) - float(s['op'] or 0), 2)
                })
            # 后一名
            if i < len(all_stores) - 1:
                next_s = all_stores[i + 1]
                result['neighbors'].append({
                    "rank": i + 2, 
                    "name": next_s['store_name'], 
                    "profit": round(float(next_s['op'] or 0), 2),
                    "diff": "lower",
                    "gap": round(float(s['op'] or 0) - float(next_s['op'] or 0), 2)
                })
            break
    
    return result
# ==================== 静态文件 ====================

# ==================== 数据导出 ====================
from io import BytesIO
from fastapi.responses import StreamingResponse
import csv

@app.get("/api/export/my-data")
def export_my_data(start_date: str = Query(...), end_date: str = Query(...), user=Depends(get_current_user)):
    """导出用户门店数据（CSV）"""
    from io import StringIO
    perms = json.loads(user.get('store_permissions', '[]'))
    is_admin = user.get('is_admin', 0)
    conn = sqlite3.connect(QNH_DB)
    conn.row_factory = sqlite3.Row
    if is_admin:
        rows = conn.execute("""SELECT date,store_name,SUM(valid_orders) as orders,SUM(sales_revenue) as revenue,SUM(sales_revenue)/NULLIF(SUM(valid_orders),0) as avg_price,SUM(refund_orders) as refunds,SUM(new_customers) as new_cust,SUM(old_customers) as old_cust FROM store_daily_full WHERE date BETWEEN ? AND ? AND valid_orders>0 GROUP BY date,store_name ORDER BY date DESC,orders DESC""", (start_date, end_date)).fetchall()
    else:
        if not perms: raise HTTPException(status_code=403, detail="无权限")
        placeholders = ','.join('?' * len(perms))
        rows = conn.execute(f"""SELECT date,store_name,SUM(valid_orders) as orders,SUM(sales_revenue) as revenue,SUM(sales_revenue)/NULLIF(SUM(valid_orders),0) as avg_price,SUM(refund_orders) as refunds,SUM(new_customers) as new_cust,SUM(old_customers) as old_cust FROM store_daily_full WHERE date BETWEEN ? AND ? AND store_name IN ({placeholders}) GROUP BY date,store_name ORDER BY date DESC,orders DESC""", (start_date, end_date, *perms)).fetchall()
    conn.close()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['日期','门店','订单数','销售额','客单价','退单数','新客数','老客数'])
    for r in rows:
        writer.writerow([r['date'],r['store_name'],r['orders'],f"{r['revenue']:.2f}" if r['revenue'] else "0.00",f"{r['avg_price']:.2f}" if r['avg_price'] else "0.00",r['refunds'],r['new_cust'],r['old_cust']])
    csv_content = '\ufeff' + output.getvalue()
    from urllib.parse import quote
    filename = quote(f"门店数据_{start_date}_{end_date}.csv")
    return StreamingResponse(iter([csv_content.encode('utf-8')]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"})

@app.get("/")
async def index():
    return FileResponse("/home/ubuntu/nofx-Metroll/dist/ranking/index.html")

app.mount("/", StaticFiles(directory="/home/ubuntu/nofx-Metroll/dist/ranking", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8899)
