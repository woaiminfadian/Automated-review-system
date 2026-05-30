"""
迁移 v4: 添加邮件暂存表和同步状态表
用于 Web 界面邮件收稿功能
"""
import sqlite3
import os

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "journal.db")


def migrate():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
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
            created_at       TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS email_sync_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    conn.close()
    print("v4 迁移完成: 已添加 email_staging 和 email_sync_state 表")


if __name__ == "__main__":
    migrate()
