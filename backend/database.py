"""
ShopEasy - E-Commerce Database Layer
Tables: users, products, categories, cart, orders, order_items, reviews
"""
import sqlite3, os, bcrypt

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shopeasy.db")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            email      TEXT UNIQUE NOT NULL,
            password   TEXT NOT NULL,
            phone      TEXT DEFAULT '',
            address    TEXT DEFAULT '',
            city       TEXT DEFAULT '',
            role       TEXT DEFAULT 'customer',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS categories (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '📦',
            slug TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            description  TEXT DEFAULT '',
            price        REAL NOT NULL,
            original_price REAL DEFAULT 0,
            category_id  INTEGER,
            image_url    TEXT DEFAULT '',
            stock        INTEGER DEFAULT 100,
            rating       REAL DEFAULT 0,
            review_count INTEGER DEFAULT 0,
            is_featured  INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(category_id) REFERENCES categories(id)
        );
        CREATE TABLE IF NOT EXISTS cart (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity   INTEGER DEFAULT 1,
            UNIQUE(user_id, product_id),
            FOREIGN KEY(user_id)    REFERENCES users(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            total          REAL NOT NULL,
            status         TEXT DEFAULT 'pending',
            payment_method TEXT DEFAULT 'cod',
            address        TEXT NOT NULL,
            city           TEXT NOT NULL,
            phone          TEXT NOT NULL,
            notes          TEXT DEFAULT '',
            created_at     TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id   INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity   INTEGER NOT NULL,
            price      REAL NOT NULL,
            FOREIGN KEY(order_id)   REFERENCES orders(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            rating     INTEGER NOT NULL,
            comment    TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(product_id, user_id),
            FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(user_id)    REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS wishlist (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            UNIQUE(user_id, product_id)
        );
    """)

    def h(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

    # Categories
    cats = [("Electronics","📱","electronics"),("Fashion","👗","fashion"),
            ("Home & Kitchen","🏠","home"),("Books","📚","books"),
            ("Sports","⚽","sports"),("Beauty","💄","beauty")]
    for ct in cats:
        c.execute("INSERT OR IGNORE INTO categories(name,icon,slug) VALUES(?,?,?)", ct)

    # Users
    for u in [("Admin User","admin@shopeasy.com",h("Admin@123"),"admin"),
              ("Rahul Kumar","user@demo.com",h("Demo@123"),"customer"),
              ("Priya Singh","priya@demo.com",h("Demo@123"),"customer")]:
        c.execute("INSERT OR IGNORE INTO users(name,email,password,role) VALUES(?,?,?,?)", u)
    conn.commit()

    def cid(slug):
        r = c.execute("SELECT id FROM categories WHERE slug=?", (slug,)).fetchone()
        return r["id"] if r else 1

    # Products
    prods = [
        ("iPhone 15 Pro","Latest Apple flagship with A17 chip, 48MP camera, titanium design",89999,99999,cid("electronics"),"https://images.unsplash.com/photo-1695048133142-1a20484d2569?w=400",50,4.8,234,1),
        ("Samsung Galaxy S24","Android flagship with AI features, 200MP camera, Snapdragon 8",79999,85999,cid("electronics"),"https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=400",75,4.7,189,1),
        ("Sony WH-1000XM5","Industry-leading noise cancelling wireless headphones",24999,29999,cid("electronics"),"https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb?w=400",120,4.9,456,1),
        ("MacBook Air M3","Ultra-thin laptop with M3 chip, 18hr battery, Liquid Retina display",114999,124999,cid("electronics"),"https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400",30,4.8,167,1),
        ("Men's Casual Shirt","Premium cotton casual shirt, breathable fabric, multiple colors",899,1499,cid("fashion"),"https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=400",500,4.3,89,0),
        ("Women's Kurti Set","Beautiful embroidered kurti with matching palazzo, festive wear",1299,1999,cid("fashion"),"https://images.unsplash.com/photo-1583391733956-6c78276477e2?w=400",350,4.5,234,0),
        ("Running Shoes","Lightweight running shoes with cushioned sole, breathable mesh",2499,3499,cid("fashion"),"https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400",200,4.6,178,1),
        ("Non-Stick Cookware Set","8-piece non-stick cookware set with glass lids, induction compatible",3999,5999,cid("home"),"https://images.unsplash.com/photo-1585515320310-259814833e62?w=400",80,4.4,123,0),
        ("Stainless Steel Water Bottle","1L insulated bottle, keeps drinks cold 24hr or hot 12hr",599,899,cid("home"),"https://images.unsplash.com/photo-1602143407151-7111542de6e8?w=400",400,4.7,567,0),
        ("Yoga Mat","Premium anti-slip yoga mat, 6mm thick, eco-friendly material",1299,1799,cid("sports"),"https://images.unsplash.com/photo-1601925228616-c833fe6b7bba?w=400",300,4.5,234,0),
        ("Dumbbell Set","Adjustable dumbbell set 2-20kg, cast iron with rubber coating",4999,6999,cid("sports"),"https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=400",60,4.6,89,1),
        ("The Psychology of Money","Timeless lessons on wealth, greed, and happiness by Morgan Housel",399,499,cid("books"),"https://images.unsplash.com/photo-1592496431122-2349e0fbc666?w=400",1000,4.9,890,1),
        ("Atomic Habits","Tiny changes, remarkable results — Build good habits by James Clear",349,449,cid("books"),"https://images.unsplash.com/photo-1513475382585-d06e58bcb0e0?w=400",800,4.8,1234,1),
        ("Face Serum","Vitamin C brightening serum, 30ml, dermatologist tested",999,1499,cid("beauty"),"https://images.unsplash.com/photo-1620916566398-39f1143ab7be?w=400",250,4.4,156,0),
        ("Smart Watch","Fitness tracker with heart rate, SpO2, GPS, 7-day battery",5999,7999,cid("electronics"),"https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400",150,4.5,345,1),
    ]
    for p in prods:
        c.execute("""INSERT OR IGNORE INTO products
            (name,description,price,original_price,category_id,image_url,stock,rating,review_count,is_featured)
            VALUES(?,?,?,?,?,?,?,?,?,?)""", p)
    conn.commit()

    # Sample cart for demo user
    uid = c.execute("SELECT id FROM users WHERE email='user@demo.com'").fetchone()
    if uid:
        for pid, qty in [(1,1),(3,1),(12,2)]:
            c.execute("INSERT OR IGNORE INTO cart(user_id,product_id,quantity) VALUES(?,?,?)",
                      (uid["id"], pid, qty))
    conn.commit()
    conn.close()
    print("✅ ShopEasy DB ready")

if __name__ == "__main__":
    init_db()
