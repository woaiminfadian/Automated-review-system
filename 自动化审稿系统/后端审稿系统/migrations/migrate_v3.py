"""
数据库迁移 v3 - 添加 password_default 列
"""
import sqlite3, os

DB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DB_DIR, "journal.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def column_exists(conn, table, col):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return col in cols


def migrate():
    conn = get_conn()
    if not column_exists(conn, "editors", "password_default"):
        conn.execute("ALTER TABLE editors ADD COLUMN password_default INTEGER DEFAULT 0")
        print("  + editors.password_default")
    conn.commit()
    conn.close()
    print("迁移 v3 完成!")


if __name__ == "__main__":
    migrate()
