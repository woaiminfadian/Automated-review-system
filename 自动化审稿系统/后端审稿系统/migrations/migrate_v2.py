"""
数据库迁移 v2 - 为编辑审稿在线系统添加字段
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

    # editors 表加字段
    editor_cols = [
        ("password_hash", "TEXT DEFAULT NULL"),
        ("last_login", "TEXT"),
    ]
    for col, typ in editor_cols:
        if not column_exists(conn, "editors", col):
            conn.execute(f"ALTER TABLE editors ADD COLUMN {col} {typ}")
            print(f"  + editors.{col}")

    # assignments 表加字段
    assign_cols = [
        ("score_topic", "REAL"),
        ("score_viewpoint", "REAL"),
        ("score_argument", "REAL"),
        ("score_standard", "REAL"),
        ("score_reference", "REAL"),
        ("score_structure", "REAL"),
        ("score_total", "REAL"),
        ("review_opinion", "TEXT"),
        ("review_comment", "TEXT"),
        ("file_review", "TEXT"),
        ("file_annotated", "TEXT"),
        ("reviewed_at", "TEXT"),
    ]
    for col, typ in assign_cols:
        if not column_exists(conn, "assignments", col):
            conn.execute(f"ALTER TABLE assignments ADD COLUMN {col} {typ}")
            print(f"  + assignments.{col}")

    conn.commit()
    conn.close()
    print("迁移完成!")


if __name__ == "__main__":
    migrate()
