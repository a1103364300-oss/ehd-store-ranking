#!/usr/bin/env python3
"""
易惠达门店排行榜 - 后端 API
"""
import sqlite3, os, secrets, string, hashlib, json
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext

DB_PATH = os.path.expanduser('~/ranking_auth.db')
QNH_DB = os.path.expanduser('~/qnh-data/qnh.db')
SECRET_KEY = "ehd-ranking-secret-2026-xK9mP2nQ"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7天

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI(title="EHD Ranking API")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── 数据库初始化 ─────────────────────────────────────────
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
    # 创建默认管理员
    c.execute("SELECT id FROM users WHERE username='admin'")
    if not c.fetchone():
        ph = pwd_context.hash("Admin2026!")
        c.execute("INSERT INTO users(username,password_hash,full_name,is_admin,store_permissions) VALUES(?,?,?,1,'[]')",
                  ('admin', ph, '超级管理员'))
        print("✅ 默认管理员已创建: admin / Admin2026!")
    conn.commit()
    conn.close()

init_db()

# ── 工具函数 ─────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

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

def require_admin(user=Depends(get_current_user)):
    if not user['is_admin']:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user

def gen_card_no():
    chars = string.ascii_uppercase + string.digits
    seg = lambda n: ''.join(secrets.choice(chars) for _ in range(n))
    return f"EHD-{seg(4)}-{seg(4)}"

# ── 获取所有门店列表 ─────────────────────────────────────
def get_all_stores():
    conn = sqlite3.connect(QNH_DB)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT store_name FROM store_daily_full WHERE valid_orders>0 ORDER BY store_name")
    stores = [r[0] for r in cur.fetchall()]
    conn.close()
    return stores

# ── Pydantic Models ──────────────────────────────────────
class RegisterReq(BaseModel):
    username: str
    password: str
    full_name: str
    card_no: str

class LoginReq(BaseModel):
    username: str
    password: str

class GenCardsReq(BaseModel):
    count: int = 1
    note: str = ""

class UpdateUserReq(BaseModel):
    is_active: Optional[int] = None
    store_permissions: Optional[List[str]] = None
    full_name: Optional[str] = None

# ── 路由 ─────────────────────────────────────────────────

@app.post("/api/register")
def register(req: RegisterReq):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # 验证邀请卡
    card = conn.execute("SELECT * FROM invite_cards WHERE card_no=?", (req.card_no.upper(),)).fetchone()
    if not card:
        conn.close(); raise HTTPException(400, "邀请卡号不存在")
    if card['is_used']:
        conn.close(); raise HTTPException(400, "该邀请卡已被使用")
    # 检查用户名
    exist = conn.execute("SELECT id FROM users WHERE username=?", (req.username,)).fetchone()
    if exist:
        conn.close(); raise HTTPException(400, "该账号已被注册")
    if len(req.password) < 6:
        conn.close(); raise HTTPException(400, "密码至少6位")
    ph = pwd_context.hash(req.password)
    conn.execute("INSERT INTO users(username,password_hash,full_name,store_permissions) VALUES(?,?,?,'[]')",
                 (req.username, ph, req.full_name))
    conn.execute("UPDATE invite_cards SET is_used=1,used_by=?,used_at=datetime('now','localtime') WHERE card_no=?",
                 (req.username, req.card_no.upper()))
    conn.commit(); conn.close()
    return {"ok": True, "msg": "注册成功，请登录"}

@app.post("/api/login")
def login(req: LoginReq):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    user = conn.execute("SELECT * FROM users WHERE username=?", (req.username,)).fetchone()
    if not user or not pwd_context.verify(req.password, user['password_hash']):
        conn.close(); raise HTTPException(401, "账号或密码错误")
    if not user['is_active']:
        conn.close(); raise HTTPException(403, "账号已被封禁，请联系管理员")
    conn.execute("UPDATE users SET last_login=datetime('now','localtime') WHERE username=?", (req.username,))
    conn.commit(); conn.close()
    token = create_token({"sub": req.username, "is_admin": user['is_admin']})
    return {"token": token, "is_admin": user['is_admin'], "full_name": user['full_name']}

@app.get("/api/me")
def me(user=Depends(get_current_user)):
    return {
        "username": user['username'],
        "full_name": user['full_name'],
        "is_admin": user['is_admin'],
        "store_permissions": json.loads(user['store_permissions'] or '[]'),
    }

@app.get("/api/stores")
def list_stores(user=Depends(get_current_user)):
    all_stores = get_all_stores()
    if user['is_admin']:
        return {"stores": all_stores}
    perms = json.loads(user['store_permissions'] or '[]')
    if not perms:
        return {"stores": all_stores}  # 空权限=全部可见
    return {"stores": [s for s in all_stores if s in perms]}

# ── 排行榜数据 API ───────────────────────────────────────
@app.get("/api/ranking")
def get_ranking(date: str = None, user=Depends(get_current_user)):
    conn = sqlite3.connect(QNH_DB)
    cur = conn.cursor()
    if not date:
        cur.execute("SELECT MAX(date) FROM store_daily_full WHERE valid_orders>0")
        date = cur.fetchone()[0]
    prev = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    
    perms = json.loads(user['store_permissions'] or '[]') if not user['is_admin'] else []
    
    cur.execute('''
        SELECT store_name, SUM(valid_orders), SUM(sales_revenue), SUM(refund_orders),
               SUM(new_customers), SUM(old_customers), SUM(merchant_discount), SUM(platform_subsidy)
        FROM store_daily_full WHERE date=? AND valid_orders>0
        GROUP BY store_name ORDER BY SUM(valid_orders) DESC
    ''', (date,))
    today_rows = cur.fetchall()
    
    cur.execute("SELECT store_name FROM store_daily_full WHERE date=? AND valid_orders>0 GROUP BY store_name ORDER BY SUM(valid_orders) DESC", (prev,))
    prev_rank = {r[0]: i+1 for i, r in enumerate(cur.fetchall())}
    
    cur.execute("SELECT SUM(valid_orders),SUM(sales_revenue),SUM(new_customers),SUM(old_customers),SUM(refund_orders) FROM store_daily_full WHERE date=?", (date,))
    s = cur.fetchone()
    conn.close()
    
    total_orders = int(s[0] or 0)
    total_revenue = round(float(s[1] or 0), 2)
    
    stores = []
    for i, row in enumerate(today_rows):
        name, orders, revenue, refund, nc, oc, disc, platform = row
        if perms and name not in perms:
            continue
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
    
    return {
        'date': date,
        'totalOrders': total_orders,
        'totalRevenue': total_revenue,
        'avgPrice': round(total_revenue/total_orders, 2) if total_orders else 0,
        'totalNew': int(s[2] or 0),
        'totalOld': int(s[3] or 0),
        'totalRefund': int(s[4] or 0),
        'stores': stores
    }

@app.get("/api/available-dates")
def available_dates(user=Depends(get_current_user)):
    conn = sqlite3.connect(QNH_DB)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT date FROM store_daily_full WHERE valid_orders>0 ORDER BY date DESC LIMIT 30")
    dates = [r[0] for r in cur.fetchall()]
    conn.close()
    return {"dates": dates}

@app.get("/api/store-history")
def store_history(name: str, user=Depends(get_current_user)):
    perms = json.loads(user['store_permissions'] or '[]') if not user['is_admin'] else []
    if perms and name not in perms:
        raise HTTPException(403, "无权查看该门店数据")
    conn = sqlite3.connect(QNH_DB)
    cur = conn.cursor()
    cur.execute('''
        SELECT date, SUM(valid_orders), SUM(sales_revenue), SUM(refund_orders),
               SUM(new_customers), SUM(old_customers), SUM(merchant_discount)
        FROM store_daily_full WHERE store_name=? AND valid_orders>0
        GROUP BY date ORDER BY date DESC LIMIT 30
    ''', (name,))
    rows = cur.fetchall()
    conn.close()
    history = [{'date': r[0], 'orders': int(r[1] or 0), 'revenue': round(float(r[2] or 0),2),
                'refundOrders': int(r[3] or 0), 'newCustomers': int(r[4] or 0),
                'oldCustomers': int(r[5] or 0), 'discount': round(float(r[6] or 0),2)} for r in rows]
    return {"name": name, "history": history}

# ── 管理员 API ───────────────────────────────────────────
@app.post("/api/admin/gen-cards")
def gen_cards(req: GenCardsReq, admin=Depends(require_admin)):
    if req.count < 1 or req.count > 50:
        raise HTTPException(400, "数量1-50")
    conn = sqlite3.connect(DB_PATH)
    cards = []
    for _ in range(req.count):
        card_no = gen_card_no()
        while conn.execute("SELECT id FROM invite_cards WHERE card_no=?", (card_no,)).fetchone():
            card_no = gen_card_no()
        conn.execute("INSERT INTO invite_cards(card_no,created_by,note) VALUES(?,?,?)",
                     (card_no, admin['username'], req.note))
        cards.append(card_no)
    conn.commit(); conn.close()
    return {"cards": cards}

@app.get("/api/admin/cards")
def list_cards(admin=Depends(require_admin)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cards = conn.execute("SELECT * FROM invite_cards ORDER BY created_at DESC").fetchall()
    conn.close()
    return {"cards": [dict(c) for c in cards]}

@app.get("/api/admin/users")
def list_users(admin=Depends(require_admin)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    users = conn.execute("SELECT id,username,full_name,is_admin,is_active,store_permissions,created_at,last_login FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return {"users": [dict(u) for u in users]}

@app.patch("/api/admin/users/{username}")
def update_user(username: str, req: UpdateUserReq, admin=Depends(require_admin)):
    if username == 'admin' and req.is_active == 0:
        raise HTTPException(400, "不能封禁超级管理员")
    conn = sqlite3.connect(DB_PATH)
    if req.is_active is not None:
        conn.execute("UPDATE users SET is_active=? WHERE username=?", (req.is_active, username))
    if req.store_permissions is not None:
        conn.execute("UPDATE users SET store_permissions=? WHERE username=?",
                     (json.dumps(req.store_permissions, ensure_ascii=False), username))
    if req.full_name is not None:
        conn.execute("UPDATE users SET full_name=? WHERE username=?", (req.full_name, username))
    conn.commit(); conn.close()
    return {"ok": True}

@app.delete("/api/admin/cards/{card_no}")
def delete_card(card_no: str, admin=Depends(require_admin)):
    conn = sqlite3.connect(DB_PATH)
    card = conn.execute("SELECT is_used FROM invite_cards WHERE card_no=?", (card_no,)).fetchone()
    if not card:
        conn.close(); raise HTTPException(404, "卡号不存在")
    if card[0]:
        conn.close(); raise HTTPException(400, "已使用的卡号不能删除")
    conn.execute("DELETE FROM invite_cards WHERE card_no=?", (card_no,))
    conn.commit(); conn.close()
    return {"ok": True}

@app.get("/api/admin/all-stores")
def admin_all_stores(admin=Depends(require_admin)):
    return {"stores": get_all_stores()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8899)
