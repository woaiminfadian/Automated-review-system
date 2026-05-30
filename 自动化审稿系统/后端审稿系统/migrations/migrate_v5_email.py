"""
迁移 v5：email_staging 增加 imported_submission_id 字段
用法: python3 migrate_v5_email.py
"""
import sqlite3, os, json

DB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DB_DIR, "journal.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. 添加 imported_submission_id 字段（如果不存在）
    cols = [c[1] for c in cur.execute("PRAGMA table_info(email_staging)").fetchall()]
    if "imported_submission_id" not in cols:
        print("添加字段: email_staging.imported_submission_id")
        cur.execute("ALTER TABLE email_staging ADD COLUMN imported_submission_id INTEGER")
        conn.commit()
    else:
        print("字段 imported_submission_id 已存在，跳过添加。")

    # 2. 尝试回填：通过 submissions.notes 中的 message_id 匹配
    staging_rows = cur.execute(
        "SELECT id, message_id FROM email_staging WHERE imported_submission_id IS NULL AND status='已录入'"
    ).fetchall()
    if staging_rows:
        print(f"尝试回填 {len(staging_rows)} 条已录入记录...")
        updated = 0
        for row in staging_rows:
            sub = cur.execute(
                "SELECT id FROM submissions WHERE notes LIKE ?",
                (f"%{row['message_id']}%",),
            ).fetchone()
            if sub:
                cur.execute(
                    "UPDATE email_staging SET imported_submission_id=? WHERE id=?",
                    (sub["id"], row["id"]),
                )
                updated += 1
        conn.commit()
        print(f"回填成功: {updated}/{len(staging_rows)}")
    else:
        print("无需回填的记录。")

    conn.close()
    print("迁移 v5 完成。")

if __name__ == "__main__":
    migrate()
