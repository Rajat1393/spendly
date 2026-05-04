import sqlite3
import os
from werkzeug.security import generate_password_hash


def get_db():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'spendly.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    if existing[0] > 0:
        conn.close()
        return

    password_hash = generate_password_hash("demo123")
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", password_hash)
    )
    conn.commit()

    user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
    ).fetchone()["id"]

    expenses = [
        (user_id, 12.50, "Food",          "2026-04-02", "Lunch at cafe"),
        (user_id, 45.00, "Transport",     "2026-04-05", "Monthly bus pass"),
        (user_id, 89.99, "Bills",         "2026-04-07", "Electricity bill"),
        (user_id, 30.00, "Health",        "2026-04-10", "Pharmacy"),
        (user_id, 15.00, "Entertainment", "2026-04-13", "Streaming subscription"),
        (user_id, 62.40, "Shopping",      "2026-04-17", "Clothing"),
        (user_id,  8.75, "Other",         "2026-04-20", "Stationery"),
        (user_id, 22.00, "Food",          "2026-04-24", "Dinner with friends"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        expenses
    )
    conn.commit()
    conn.close()


def create_expense(user_id, amount, category, date, description):
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date, description),
    )
    conn.commit()
    conn.close()
    return cursor.lastrowid


def create_user(name, email, password_hash):
    conn = get_db()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, password_hash)
    )
    conn.commit()
    conn.close()


def get_user_by_email(email):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return user


def get_recent_expenses(user_id, limit=5, *, date_from=None, date_to=None):
    conn = get_db()
    query = """
        SELECT id, amount, category, date, description
        FROM   expenses
        WHERE  user_id = ?
        """
    params = [user_id]
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    query += " ORDER BY date DESC, created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_expense_stats(user_id, *, date_from=None, date_to=None):
    conn = get_db()
    query = """
        SELECT COALESCE(SUM(amount), 0) AS total_spent,
               COUNT(*)                 AS transaction_count
        FROM   expenses
        WHERE  user_id = ?
        """
    params = [user_id]
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    row = conn.execute(query, params).fetchone()
    conn.close()
    return {
        "total_spent":       float(row["total_spent"]),
        "transaction_count": int(row["transaction_count"]),
    }


def get_category_totals(user_id, *, date_from=None, date_to=None):
    conn = get_db()
    query = """
        SELECT category    AS name,
               SUM(amount) AS total
        FROM   expenses
        WHERE  user_id = ?
        """
    params = [user_id]
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    query += " GROUP BY category ORDER BY total DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [{"name": row["name"], "total": float(row["total"])} for row in rows]


def get_top_category(user_id, *, date_from=None, date_to=None):
    conn = get_db()
    query = """
        SELECT category
        FROM   expenses
        WHERE  user_id = ?
        """
    params = [user_id]
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    query += " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1"
    row = conn.execute(query, params).fetchone()
    conn.close()
    return row["category"] if row else "—"
