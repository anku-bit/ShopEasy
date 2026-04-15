"""
ShopEasy - E-Commerce Backend
Routes: Auth, Products, Cart, Orders, Reviews, Wishlist, Admin
"""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os, bcrypt, jwt, datetime, functools, re

from database import get_db, init_db

app = Flask(__name__, static_folder="../frontend/public", static_url_path="")
CORS(app, origins="*")
SECRET = os.environ.get("SECRET_KEY", "shopeasy_secret_2024")

# ── helpers ──────────────────────────────────────
def hash_pw(p):    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
def check_pw(p,h): return bcrypt.checkpw(p.encode(), h.encode())
def make_tok(uid, role):
    return jwt.encode({"uid":uid,"role":role,
        "exp": datetime.datetime.utcnow()+datetime.timedelta(days=30)},SECRET,algorithm="HS256")
def decode_tok(tok):
    try: return jwt.decode(tok, SECRET, algorithms=["HS256"])
    except: return None
def cur_user():
    auth = request.headers.get("Authorization","")
    if not auth.startswith("Bearer "): return None
    d = decode_tok(auth[7:])
    if not d: return None
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id=?", (d["uid"],)).fetchone()
    conn.close()
    return dict(u) if u else None
def auth(roles=None):
    def dec(fn):
        @functools.wraps(fn)
        def wrap(*a,**kw):
            u = cur_user()
            if not u: return jsonify({"error":"Login required"}), 401
            if roles and u["role"] not in roles: return jsonify({"error":"Access denied"}), 403
            request.user = u
            return fn(*a,**kw)
        return wrap
    return dec
def safe(t,n=2000): return str(t or "").strip()[:n]

# ── AUTH ─────────────────────────────────────────
@app.route("/api/auth/register", methods=["POST"])
def register():
    d = request.json or {}
    name  = safe(d.get("name"))
    email = safe(d.get("email")).lower()
    pw    = d.get("password","")
    if not name or not email or not pw:
        return jsonify({"error":"Name, email, password required"}), 400
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"error":"Invalid email"}), 400
    if len(pw) < 6:
        return jsonify({"error":"Password min 6 characters"}), 400
    conn = get_db()
    try:
        row = conn.execute(
            "INSERT INTO users(name,email,password) VALUES(?,?,?) RETURNING id",
            (name, email, hash_pw(pw))).fetchone()
        conn.commit()
        uid = row["id"]
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        return jsonify({"token": make_tok(uid,"customer"),
                        "user": {k:v for k,v in dict(user).items() if k!="password"}}), 201
    except Exception as e:
        conn.close()
        if "UNIQUE" in str(e): return jsonify({"error":"Email already registered"}), 409
        return jsonify({"error":str(e)}), 500

@app.route("/api/auth/login", methods=["POST"])
def login():
    d  = request.json or {}
    em = safe(d.get("email","")).lower()
    pw = d.get("password","")
    if not em or not pw: return jsonify({"error":"Email and password required"}), 400
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE email=?", (em,)).fetchone()
    conn.close()
    if not u or not check_pw(pw, u["password"]):
        return jsonify({"error":"Invalid email or password"}), 401
    return jsonify({"token": make_tok(u["id"], u["role"]),
                    "user": {k:v for k,v in dict(u).items() if k!="password"}})

@app.route("/api/auth/me", methods=["GET"])
@auth()
def me():
    u = request.user
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
    cart_count = conn.execute("SELECT COALESCE(SUM(quantity),0) FROM cart WHERE user_id=?", (u["id"],)).fetchone()[0]
    conn.close()
    r = {k:v for k,v in dict(user).items() if k!="password"}
    r["cart_count"] = cart_count
    return jsonify(r)

@app.route("/api/auth/update", methods=["PUT"])
@auth()
def update_profile():
    u, d = request.user, request.json or {}
    conn = get_db()
    cur  = conn.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
    f = {k: safe(d.get(k, cur[k] or "")) for k in ["name","phone","address","city"]}
    conn.execute("UPDATE users SET name=?,phone=?,address=?,city=? WHERE id=?",
                 (*f.values(), u["id"]))
    conn.commit()
    updated = conn.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
    conn.close()
    return jsonify({k:v for k,v in dict(updated).items() if k!="password"})

# ── CATEGORIES ───────────────────────────────────
@app.route("/api/categories", methods=["GET"])
def categories():
    conn = get_db()
    rows = conn.execute("""SELECT c.*, COUNT(p.id) as product_count
        FROM categories c LEFT JOIN products p ON p.category_id=c.id
        GROUP BY c.id ORDER BY c.name""").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ── PRODUCTS ─────────────────────────────────────
@app.route("/api/products", methods=["GET"])
def products():
    search   = request.args.get("search","")
    cat      = request.args.get("category","")
    sort     = request.args.get("sort","newest")
    featured = request.args.get("featured","")
    page     = max(1, int(request.args.get("page",1)))
    per_page = int(request.args.get("per_page",12))
    min_p    = float(request.args.get("min_price",0))
    max_p    = float(request.args.get("max_price",9999999))

    q = """SELECT p.*, c.name as cat_name, c.icon as cat_icon
           FROM products p LEFT JOIN categories c ON p.category_id=c.id
           WHERE p.price>=? AND p.price<=?"""
    params = [min_p, max_p]
    if search:
        q += " AND (p.name LIKE ? OR p.description LIKE ?)"
        params += [f"%{search}%"]*2
    if cat:
        q += " AND c.slug=?"
        params.append(cat)
    if featured:
        q += " AND p.is_featured=1"
    order = {"newest":"p.created_at DESC","price_low":"p.price ASC",
             "price_high":"p.price DESC","rating":"p.rating DESC",
             "popular":"p.review_count DESC"}.get(sort,"p.created_at DESC")
    q += f" ORDER BY {order}"

    conn = get_db()
    rows  = conn.execute(q, params).fetchall()
    total = len(rows)
    start = (page-1)*per_page
    conn.close()
    return jsonify({"products":[dict(r) for r in rows[start:start+per_page]],
                    "total":total,"page":page,"pages":(total+per_page-1)//per_page})

@app.route("/api/products/<int:pid>", methods=["GET"])
def get_product(pid):
    conn = get_db()
    p = conn.execute("""SELECT p.*, c.name as cat_name, c.icon as cat_icon
        FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE p.id=?""", (pid,)).fetchone()
    if not p: conn.close(); return jsonify({"error":"Not found"}), 404
    reviews = conn.execute("""SELECT r.*, u.name as user_name
        FROM reviews r JOIN users u ON r.user_id=u.id
        WHERE r.product_id=? ORDER BY r.created_at DESC LIMIT 10""", (pid,)).fetchall()
    related = conn.execute("""SELECT * FROM products
        WHERE category_id=? AND id!=? LIMIT 4""", (p["category_id"], pid)).fetchall()
    conn.close()
    return jsonify({"product":dict(p),"reviews":[dict(r) for r in reviews],
                    "related":[dict(r) for r in related]})

@app.route("/api/products", methods=["POST"])
@auth(["admin"])
def add_product():
    d = request.json or {}
    name  = safe(d.get("name",""))
    price = float(d.get("price",0))
    if not name or price <= 0: return jsonify({"error":"Name and price required"}), 400
    conn = get_db()
    row = conn.execute("""INSERT INTO products
        (name,description,price,original_price,category_id,image_url,stock,is_featured)
        VALUES(?,?,?,?,?,?,?,?) RETURNING id""",
        (name, safe(d.get("description","")), price,
         float(d.get("original_price",price)), d.get("category_id"),
         safe(d.get("image_url","")), int(d.get("stock",100)),
         int(d.get("is_featured",0)))).fetchone()
    conn.commit()
    conn.close()
    return jsonify({"message":"Product added","id":row["id"]}), 201

@app.route("/api/products/<int:pid>", methods=["PUT"])
@auth(["admin"])
def update_product(pid):
    d, conn = request.json or {}, get_db()
    p = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not p: conn.close(); return jsonify({"error":"Not found"}), 404
    f = {k: d.get(k, p[k]) for k in ["name","description","price","original_price","stock","is_featured","image_url"]}
    conn.execute("UPDATE products SET name=?,description=?,price=?,original_price=?,stock=?,is_featured=?,image_url=? WHERE id=?",
                 (*f.values(), pid))
    conn.commit(); conn.close()
    return jsonify({"message":"Updated"})

@app.route("/api/products/<int:pid>", methods=["DELETE"])
@auth(["admin"])
def del_product(pid):
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit(); conn.close()
    return jsonify({"message":"Deleted"})

# ── CART ─────────────────────────────────────────
@app.route("/api/cart", methods=["GET"])
@auth()
def get_cart():
    u = request.user
    conn = get_db()
    rows = conn.execute("""SELECT c.id, c.quantity, p.id as product_id, p.name,
        p.price, p.original_price, p.image_url, p.stock
        FROM cart c JOIN products p ON c.product_id=p.id
        WHERE c.user_id=? ORDER BY c.id DESC""", (u["id"],)).fetchall()
    conn.close()
    items = [dict(r) for r in rows]
    total = sum(r["price"]*r["quantity"] for r in items)
    return jsonify({"items":items,"total":round(total,2),"count":sum(r["quantity"] for r in items)})

@app.route("/api/cart", methods=["POST"])
@auth()
def add_to_cart():
    u, d = request.user, request.json or {}
    pid = d.get("product_id")
    qty = int(d.get("quantity",1))
    if not pid or qty < 1: return jsonify({"error":"product_id and quantity required"}), 400
    conn = get_db()
    existing = conn.execute("SELECT id,quantity FROM cart WHERE user_id=? AND product_id=?",
                             (u["id"],pid)).fetchone()
    if existing:
        conn.execute("UPDATE cart SET quantity=? WHERE id=?", (existing["quantity"]+qty, existing["id"]))
    else:
        conn.execute("INSERT INTO cart(user_id,product_id,quantity) VALUES(?,?,?)", (u["id"],pid,qty))
    conn.commit()
    count = conn.execute("SELECT COALESCE(SUM(quantity),0) FROM cart WHERE user_id=?", (u["id"],)).fetchone()[0]
    conn.close()
    return jsonify({"message":"Added to cart","cart_count":count}), 201

@app.route("/api/cart/<int:cid>", methods=["PUT"])
@auth()
def update_cart(cid):
    u, d = request.user, request.json or {}
    qty  = int(d.get("quantity",1))
    conn = get_db()
    if qty <= 0:
        conn.execute("DELETE FROM cart WHERE id=? AND user_id=?", (cid, u["id"]))
    else:
        conn.execute("UPDATE cart SET quantity=? WHERE id=? AND user_id=?", (qty, cid, u["id"]))
    conn.commit(); conn.close()
    return jsonify({"message":"Updated"})

@app.route("/api/cart/<int:cid>", methods=["DELETE"])
@auth()
def remove_from_cart(cid):
    u = request.user
    conn = get_db()
    conn.execute("DELETE FROM cart WHERE id=? AND user_id=?", (cid, u["id"]))
    conn.commit(); conn.close()
    return jsonify({"message":"Removed"})

@app.route("/api/cart/clear", methods=["DELETE"])
@auth()
def clear_cart():
    u = request.user
    conn = get_db()
    conn.execute("DELETE FROM cart WHERE user_id=?", (u["id"],))
    conn.commit(); conn.close()
    return jsonify({"message":"Cart cleared"})

# ── ORDERS ───────────────────────────────────────
@app.route("/api/orders", methods=["POST"])
@auth()
def place_order():
    u, d = request.user, request.json or {}
    address = safe(d.get("address",""))
    city    = safe(d.get("city",""))
    phone   = safe(d.get("phone",""))
    if not address or not city or not phone:
        return jsonify({"error":"Address, city, phone required"}), 400
    conn = get_db()
    cart = conn.execute("""SELECT c.*, p.price, p.stock FROM cart c
        JOIN products p ON c.product_id=p.id WHERE c.user_id=?""", (u["id"],)).fetchall()
    if not cart: conn.close(); return jsonify({"error":"Cart is empty"}), 400
    total = sum(c["price"]*c["quantity"] for c in cart)
    row = conn.execute("""INSERT INTO orders(user_id,total,address,city,phone,payment_method,notes)
        VALUES(?,?,?,?,?,?,?) RETURNING id""",
        (u["id"],total,address,city,phone,
         d.get("payment_method","cod"), safe(d.get("notes","")))).fetchone()
    oid = row["id"]
    for item in cart:
        conn.execute("INSERT INTO order_items(order_id,product_id,quantity,price) VALUES(?,?,?,?)",
                     (oid, item["product_id"], item["quantity"], item["price"]))
        conn.execute("UPDATE products SET stock=stock-? WHERE id=?",
                     (item["quantity"], item["product_id"]))
    conn.execute("DELETE FROM cart WHERE user_id=?", (u["id"],))
    conn.commit(); conn.close()
    return jsonify({"message":"Order placed!","order_id":oid}), 201

@app.route("/api/orders", methods=["GET"])
@auth()
def get_orders():
    u = request.user
    conn = get_db()
    if u["role"] == "admin":
        rows = conn.execute("""SELECT o.*, u.name as user_name, u.email as user_email
            FROM orders o JOIN users u ON o.user_id=u.id ORDER BY o.created_at DESC""").fetchall()
    else:
        rows = conn.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (u["id"],)).fetchall()
    result = []
    for r in rows:
        items = conn.execute("""SELECT oi.*, p.name as product_name, p.image_url
            FROM order_items oi JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?""",
            (r["id"],)).fetchall()
        result.append({**dict(r), "items":[dict(i) for i in items]})
    conn.close()
    return jsonify(result)

@app.route("/api/orders/<int:oid>/status", methods=["PUT"])
@auth(["admin"])
def update_order_status(oid):
    status = (request.json or {}).get("status","")
    valid  = ["pending","confirmed","shipped","delivered","cancelled"]
    if status not in valid: return jsonify({"error":f"Status must be one of {valid}"}), 400
    conn = get_db()
    conn.execute("UPDATE orders SET status=? WHERE id=?", (status, oid))
    conn.commit(); conn.close()
    return jsonify({"message":"Status updated"})

# ── REVIEWS ──────────────────────────────────────
@app.route("/api/products/<int:pid>/reviews", methods=["POST"])
@auth()
def add_review(pid):
    u, d = request.user, request.json or {}
    rating  = int(d.get("rating",0))
    comment = safe(d.get("comment",""), 500)
    if rating not in range(1,6): return jsonify({"error":"Rating 1-5 required"}), 400
    conn = get_db()
    try:
        conn.execute("INSERT INTO reviews(product_id,user_id,rating,comment) VALUES(?,?,?,?)",
                     (pid, u["id"], rating, comment))
        avg = conn.execute("SELECT AVG(rating) as a, COUNT(*) as c FROM reviews WHERE product_id=?",
                           (pid,)).fetchone()
        conn.execute("UPDATE products SET rating=?,review_count=? WHERE id=?",
                     (round(avg["a"],1), avg["c"], pid))
        conn.commit(); conn.close()
        return jsonify({"message":"Review added"}), 201
    except Exception as e:
        conn.close()
        if "UNIQUE" in str(e): return jsonify({"error":"Already reviewed"}), 409
        return jsonify({"error":str(e)}), 500

# ── WISHLIST ─────────────────────────────────────
@app.route("/api/wishlist", methods=["GET"])
@auth()
def get_wishlist():
    u = request.user
    conn = get_db()
    rows = conn.execute("""SELECT w.id, p.* FROM wishlist w
        JOIN products p ON w.product_id=p.id WHERE w.user_id=? ORDER BY w.id DESC""",
        (u["id"],)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/wishlist", methods=["POST"])
@auth()
def toggle_wishlist():
    u, d = request.user, request.json or {}
    pid = d.get("product_id")
    conn = get_db()
    ex = conn.execute("SELECT id FROM wishlist WHERE user_id=? AND product_id=?",
                      (u["id"],pid)).fetchone()
    if ex:
        conn.execute("DELETE FROM wishlist WHERE user_id=? AND product_id=?", (u["id"],pid))
        saved = False
    else:
        conn.execute("INSERT INTO wishlist(user_id,product_id) VALUES(?,?)", (u["id"],pid))
        saved = True
    conn.commit(); conn.close()
    return jsonify({"saved":saved})

# ── ADMIN STATS ──────────────────────────────────
@app.route("/api/admin/stats", methods=["GET"])
@auth(["admin"])
def admin_stats():
    conn = get_db()
    s = {
        "total_users":    conn.execute("SELECT COUNT(*) FROM users WHERE role='customer'").fetchone()[0],
        "total_products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "total_orders":   conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "total_revenue":  conn.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='cancelled'").fetchone()[0],
        "pending_orders": conn.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0],
        "low_stock":      conn.execute("SELECT COUNT(*) FROM products WHERE stock<10").fetchone()[0],
    }
    recent = conn.execute("""SELECT o.*, u.name as user_name FROM orders o
        JOIN users u ON o.user_id=u.id ORDER BY o.created_at DESC LIMIT 5""").fetchall()
    conn.close()
    return jsonify({"stats":s,"recent_orders":[dict(r) for r in recent]})

@app.route("/api/admin/users", methods=["GET"])
@auth(["admin"])
def admin_users():
    conn = get_db()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify([{k:v for k,v in dict(r).items() if k!="password"} for r in rows])

# ── SEARCH SUGGEST ────────────────────────────────
@app.route("/api/search/suggest", methods=["GET"])
def suggest():
    q = request.args.get("q","")
    if len(q) < 2: return jsonify([])
    conn = get_db()
    rows = conn.execute("SELECT id,name,price FROM products WHERE name LIKE ? LIMIT 6",
                        (f"%{q}%",)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ── FRONTEND ─────────────────────────────────────
@app.route("/", defaults={"path":""})
@app.route("/<path:path>")
def serve(path):
    fp = os.path.join(app.static_folder, path)
    if path and os.path.exists(fp): return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")

if __name__ == "__main__":
    init_db()
    print("\n" + "="*50)
    print("  🛒  ShopEasy — E-Commerce Store")
    print("  🌐  http://localhost:5001")
    print("="*50)
    print("  user@demo.com / Demo@123")
    print("  admin@shopeasy.com / Admin@123")
    print("="*50+"\n")
    app.run(debug=True, port=5001, host="0.0.0.0")
