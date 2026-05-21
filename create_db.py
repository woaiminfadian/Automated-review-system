"""
创建学报数据库 - SQLite
"""
import sqlite3, os, json
from datetime import date

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "journal.db")
CONFIG_PATH = os.path.join(DB_DIR, "..", "0. 自动化工具", "automation.config.json")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS authors (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            email       TEXT,
            phone       TEXT,
            address     TEXT,
            affiliation TEXT,
            department  TEXT,
            grade       TEXT,
            notes       TEXT,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            field           TEXT NOT NULL,
            sub_field       TEXT,
            submission_type TEXT DEFAULT '正常来稿',
            author1_id      INTEGER REFERENCES authors(id),
            author2_id      INTEGER REFERENCES authors(id),
            received_date   TEXT NOT NULL,
            status          TEXT DEFAULT '待处理',
            issue           TEXT,
            file_path       TEXT,
            notes           TEXT,
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            updated_at      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS editors (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL UNIQUE,
            email    TEXT,
            role     TEXT DEFAULT '编辑',
            subjects TEXT,
            notes    TEXT,
            active   INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS assignments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id   INTEGER NOT NULL REFERENCES submissions(id),
            editor_id       INTEGER NOT NULL REFERENCES editors(id),
            round           TEXT NOT NULL DEFAULT '一审',
            assigned_date   TEXT NOT NULL,
            deadline        TEXT,
            status          TEXT DEFAULT '待审',
            result          TEXT,
            result_date     TEXT,
            opinion_summary TEXT,
            notes           TEXT,
            created_at      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id   INTEGER,
            action      TEXT NOT NULL,
            detail      TEXT,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_submissions_field ON submissions(field);
        CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
        CREATE INDEX IF NOT EXISTS idx_submissions_date ON submissions(received_date);
        CREATE INDEX IF NOT EXISTS idx_assignments_submission ON assignments(submission_id);
        CREATE INDEX IF NOT EXISTS idx_assignments_editor ON assignments(editor_id);
    """)


def log(conn, entity_type, entity_id, action, detail=""):
    conn.execute(
        "INSERT INTO activity_log (entity_type, entity_id, action, detail) VALUES (?,?,?,?)",
        (entity_type, entity_id, action, detail),
    )


def import_editors_from_config(conn):
    if not os.path.exists(CONFIG_PATH):
        print("未找到 config 文件，跳过编辑导入")
        return
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    contacts = cfg.get("editor_contacts", {})
    for name, info in contacts.items():
        subjects = info.get("subjects", [])
        conn.execute(
            "INSERT OR IGNORE INTO editors (name, email, subjects) VALUES (?,?,?)",
            (name, info.get("email", ""), json.dumps(subjects, ensure_ascii=False)),
        )
    conn.commit()
    print(f"已导入 {len(contacts)} 位编辑信息")


def init_database():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = get_connection()
    create_tables(conn)
    import_editors_from_config(conn)
    conn.close()
    print(f"数据库已创建: {DB_PATH}")


if __name__ == "__main__":
    init_database()
