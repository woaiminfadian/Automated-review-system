"""
创建学报数据库 - SQLite
"""
import sqlite3, os, json
from datetime import date

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "journal.db")
CONFIG_PATH = os.path.join(DB_DIR, "automation.config.json")


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
            updated_at      TEXT DEFAULT (datetime('now','localtime')),
            workflow_stage  TEXT DEFAULT '待匿名',
            current_round   TEXT DEFAULT '一审',
            final_decision  TEXT,
            needs_author_reply INTEGER DEFAULT 0,
            author_replied_at TEXT,
            anonymized      INTEGER DEFAULT 0,
            anonymous_file_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS editors (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL UNIQUE,
            email         TEXT,
            role          TEXT DEFAULT '编辑',
            subjects      TEXT,
            password_hash TEXT,
            last_login    TEXT,
            notes         TEXT,
            active        INTEGER DEFAULT 1,
            password_default INTEGER DEFAULT 0
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
            -- 审稿评分字段 (6项，匹配审稿评分表)
            score_topic     REAL,
            score_viewpoint REAL,
            score_argument  REAL,
            score_standard  REAL,
            score_reference REAL,
            score_structure REAL,
            score_total     REAL,
            review_opinion  TEXT,
            review_comment  TEXT,
            file_review     TEXT,
            file_annotated  TEXT,
            reviewed_at     TEXT,
            reviewed_at     TEXT,
            notes           TEXT,
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            review_round_id INTEGER REFERENCES review_rounds(id),
            editor_recommendation TEXT,
            returned        INTEGER DEFAULT 0
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

        CREATE TABLE IF NOT EXISTS email_staging (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            uid              TEXT NOT NULL,
            message_id       TEXT NOT NULL UNIQUE,
            subject_line     TEXT,
            sender           TEXT,
            sender_name      TEXT,
            sent_at          TEXT,
            title            TEXT,
            field            TEXT,
            authors_json     TEXT DEFAULT '[]',
            author_info      TEXT,
            contact_info     TEXT,
            body_text        TEXT,
            attachments_json TEXT DEFAULT '[]',
            needs_review     INTEGER DEFAULT 1,
            status           TEXT DEFAULT '待录入',
            imported_submission_id INTEGER,
            created_at       TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS email_sync_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_assignments_editor ON assignments(editor_id);

        CREATE TABLE IF NOT EXISTS submission_files (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id   INTEGER NOT NULL REFERENCES submissions(id),
            filename        TEXT NOT NULL,
            file_path       TEXT NOT NULL,
            file_type       TEXT DEFAULT '附件',
            source          TEXT DEFAULT 'email',
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            round_name      TEXT,
            version_label   TEXT,
            uploaded_by_role TEXT,
            related_assignment_id INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_submission_files_sub
            ON submission_files(submission_id);

        CREATE TABLE IF NOT EXISTS review_rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
            round_name TEXT NOT NULL,
            status TEXT DEFAULT '未开始',
            chief_decision TEXT,
            decision_date TEXT,
            author_reply_status TEXT DEFAULT '无需回复',
            author_replied_at TEXT,
            revision_due_at TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_review_rounds_sub
            ON review_rounds(submission_id);
        CREATE INDEX IF NOT EXISTS idx_review_rounds_status
            ON review_rounds(status);

        CREATE TABLE IF NOT EXISTS author_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
            review_round_id INTEGER REFERENCES review_rounds(id),
            notification_type TEXT,
            result_label TEXT,
            subject TEXT,
            body TEXT,
            draft_path TEXT,
            status TEXT DEFAULT '草稿',
            sent_at TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_author_notif_sub
            ON author_notifications(submission_id);
    """)



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
