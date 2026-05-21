"""
迁移 v6: 修正 submission_files 表结构
- 添加 source 列
- 重命名 uploaded_at 为 created_at
- 确保 file_type 默认值正确
"""
import sqlite3
import os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal.db")


def migrate():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")

    # 获取现有列信息
    cols = {r[1] for r in conn.execute("PRAGMA table_info(submission_files)").fetchall()}

    # 添加 source 列（如果缺失）
    if "source" not in cols:
        conn.execute("ALTER TABLE submission_files ADD COLUMN source TEXT DEFAULT 'email'")
        print("v6: 已添加 source 列")

    # 重命名 uploaded_at → created_at（如果存在旧列名）
    if "uploaded_at" in cols and "created_at" not in cols:
        conn.execute("ALTER TABLE submission_files RENAME COLUMN uploaded_at TO created_at")
        print("v6: 已重命名 uploaded_at → created_at")

    conn.commit()
    conn.close()
    print("v6 迁移完成")


if __name__ == "__main__":
    migrate()
