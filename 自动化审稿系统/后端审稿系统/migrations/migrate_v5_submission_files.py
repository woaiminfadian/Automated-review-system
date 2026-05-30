"""
迁移 v5: 添加 submission_files 表 + 从现有 file_path 迁移数据
"""
import sqlite3
import os

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "journal.db")


def migrate():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS submission_files (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id   INTEGER NOT NULL REFERENCES submissions(id),
            filename        TEXT NOT NULL,
            file_path       TEXT NOT NULL,
            file_type       TEXT DEFAULT '原稿',
            uploaded_at     TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_submission_files_sub
            ON submission_files(submission_id);
    """)

    # 从现有 submissions.file_path 迁移到 submission_files
    rows = conn.execute(
        "SELECT id, file_path FROM submissions WHERE file_path IS NOT NULL AND file_path != ''"
    ).fetchall()
    migrated = 0
    for sid, fp in rows:
        exists = conn.execute(
            "SELECT COUNT(*) FROM submission_files WHERE submission_id=? AND file_path=?",
            (sid, fp),
        ).fetchone()[0]
        if not exists:
            fname = os.path.basename(fp)
            conn.execute(
                "INSERT INTO submission_files (submission_id, filename, file_path, file_type) VALUES (?,?,?,?)",
                (sid, fname, fp, "原稿"),
            )
            migrated += 1

    conn.commit()
    conn.close()
    print(f"v5 迁移完成: 已添加 submission_files 表，从现有数据迁移 {migrated} 条记录")


if __name__ == "__main__":
    migrate()
