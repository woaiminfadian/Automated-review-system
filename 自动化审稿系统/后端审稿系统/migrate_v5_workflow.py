"""
v5 数据库迁移 — 审稿流程主线优化
新增: review_rounds, author_notifications 表 + submissions/assignments/submission_files 新字段 + 回填

幂等: 可重复运行。迁移前自动备份 journal.db → journal.db.bak.v5
用法: python3 migrate_v5_workflow.py
"""
import sqlite3
import os
import shutil
from datetime import datetime

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "journal.db")
BACKUP_PATH = os.path.join(DB_DIR, "journal.db.bak.v5")


def backup():
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"[备份] {DB_PATH} → {BACKUP_PATH}")
    else:
        print("[跳过] journal.db 不存在，无需备份")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def column_exists(conn, table, column):
    """检查表中是否已存在某列"""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def table_exists(conn, table):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchall()
    return len(rows) > 0


def add_column_if_missing(conn, table, column, col_def):
    if not column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
        print(f"  + {table}.{column} ({col_def})")
    else:
        print(f"  - {table}.{column} 已存在，跳过")


def migrate():
    conn = get_conn()

    # ── submissions 新字段 ──
    print("\n[submissions 新字段]")
    new_cols = [
        ("workflow_stage", "TEXT DEFAULT '待匿名'"),
        ("current_round", "TEXT DEFAULT '一审'"),
        ("final_decision", "TEXT"),
        ("needs_author_reply", "INTEGER DEFAULT 0"),
        ("author_replied_at", "TEXT"),
        ("anonymized", "INTEGER DEFAULT 0"),
        ("anonymous_file_id", "INTEGER"),
    ]
    for col, defn in new_cols:
        add_column_if_missing(conn, "submissions", col, defn)

    # ── review_rounds 表 ──
    print("\n[review_rounds 表]")
    if not table_exists(conn, "review_rounds"):
        conn.execute("""
            CREATE TABLE review_rounds (
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
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_review_rounds_sub ON review_rounds(submission_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_review_rounds_status ON review_rounds(status)"
        )
        print("  + review_rounds 表已创建")
    else:
        print("  - review_rounds 表已存在，跳过")

    # ── assignments 新字段 ──
    print("\n[assignments 新字段]")
    add_column_if_missing(conn, "assignments", "review_round_id", "INTEGER REFERENCES review_rounds(id)")
    add_column_if_missing(conn, "assignments", "editor_recommendation", "TEXT")
    add_column_if_missing(conn, "assignments", "returned", "INTEGER DEFAULT 0")

    # ── submission_files 新字段 ──
    print("\n[submission_files 新字段]")
    add_column_if_missing(conn, "submission_files", "round_name", "TEXT")
    add_column_if_missing(conn, "submission_files", "version_label", "TEXT")
    add_column_if_missing(conn, "submission_files", "uploaded_by_role", "TEXT")
    add_column_if_missing(conn, "submission_files", "related_assignment_id", "INTEGER")

    # ── author_notifications 表 ──
    print("\n[author_notifications 表]")
    if not table_exists(conn, "author_notifications"):
        conn.execute("""
            CREATE TABLE author_notifications (
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
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_author_notif_sub ON author_notifications(submission_id)"
        )
        print("  + author_notifications 表已创建")
    else:
        print("  - author_notifications 表已存在，跳过")

    conn.commit()

    # ── 回填既有数据 ──
    backfill(conn)

    conn.close()
    print("\n迁移完成。")


def backfill(conn):
    """回填既有数据: review_rounds + assignments.review_round_id + submissions.workflow_stage"""
    print("\n[回填既有数据]")

    # 1. 获取所有已有的 assignment，按 (submission_id, round) 去重创建 review_rounds
    assigns = conn.execute("""
        SELECT DISTINCT submission_id, round
        FROM assignments
        WHERE round IS NOT NULL AND round != ''
        ORDER BY submission_id, round
    """).fetchall()

    created_rounds = 0
    for a in assigns:
        # 检查是否已存在
        existing = conn.execute(
            "SELECT id FROM review_rounds WHERE submission_id=? AND round_name=?",
            (a["submission_id"], a["round"]),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO review_rounds (submission_id, round_name, status) VALUES (?,?,?)",
                (a["submission_id"], a["round"], "未开始"),
            )
            created_rounds += 1
    print(f"  review_rounds 新建: {created_rounds} 条")

    # 2. 回填 assignments.review_round_id
    updated = 0
    for a in assigns:
        rr = conn.execute(
            "SELECT id FROM review_rounds WHERE submission_id=? AND round_name=?",
            (a["submission_id"], a["round"]),
        ).fetchone()
        if rr:
            conn.execute(
                "UPDATE assignments SET review_round_id=? WHERE submission_id=? AND round=? AND review_round_id IS NULL",
                (rr["id"], a["submission_id"], a["round"]),
            )
            updated += conn.total_changes
    print(f"  assignments.review_round_id 回填: {updated} 条")

    # 3. 回填 assignments.returned (已返回/已通过/返修/退稿 → returned=1)
    returned_cnt = conn.execute("""
        UPDATE assignments SET returned=1
        WHERE returned=0 AND status IN ('已返回','已通过','返修','退稿')
    """).rowcount
    print(f"  assignments.returned 回填: {returned_cnt} 条")

    # 4. 回填 assignments.editor_recommendation ← assignments.result
    rec_cnt = conn.execute("""
        UPDATE assignments
        SET editor_recommendation = CASE
            WHEN result IN ('通过','已通过','录用') THEN '通过'
            WHEN result IN ('修改','修改后录用','修改后录用(再审)','再审','返修') THEN '返修'
            WHEN result = '退稿' THEN '退稿'
            ELSE NULL
        END
        WHERE editor_recommendation IS NULL AND result IS NOT NULL AND result != ''
    """).rowcount
    print(f"  assignments.editor_recommendation 回填: {rec_cnt} 条")

    # 5. 回填 submissions.workflow_stage（仅对 workflow_stage IS NULL 或仍为默认 '待匿名' 的稿件）
    submissions = conn.execute("SELECT id, status FROM submissions").fetchall()
    stage_map = {
        "待处理": "待匿名",
        "派稿中": "一审中",
        "审稿中": "一审中",
        "返修中": "待作者返修",
        "已录用": "已通过三审",
        "已退稿": "已退稿",
        "作者撤稿": "作者撤稿",
    }
    wf_updated = 0
    for s in submissions:
        new_stage = stage_map.get(s["status"])
        if new_stage:
            # 检查是否已有 workflow_stage
            cur = conn.execute(
                "SELECT workflow_stage FROM submissions WHERE id=?", (s["id"],)
            ).fetchone()
            if cur and (cur["workflow_stage"] is None or cur["workflow_stage"] == "待匿名"):
                conn.execute(
                    "UPDATE submissions SET workflow_stage=? WHERE id=?",
                    (new_stage, s["id"]),
                )
                wf_updated += 1
    print(f"  submissions.workflow_stage 回填: {wf_updated} 条")

    # 6. 回填 submissions.current_round
    for s in submissions:
        max_round = conn.execute("""
            SELECT round_name FROM review_rounds
            WHERE submission_id=? ORDER BY round_name DESC LIMIT 1
        """, (s["id"],)).fetchone()
        if max_round:
            conn.execute(
                "UPDATE submissions SET current_round=? WHERE id=? AND (current_round IS NULL OR current_round='一审')",
                (max_round["round_name"], s["id"]),
            )

    # 7. 对 status='待处理' 的稿件自动创建一审 review_rounds
    pending = conn.execute(
        "SELECT id FROM submissions WHERE status='待处理'"
    ).fetchall()
    for s in pending:
        exists = conn.execute(
            "SELECT id FROM review_rounds WHERE submission_id=? AND round_name='一审'",
            (s["id"],),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO review_rounds (submission_id, round_name, status) VALUES (?,?,?)",
                (s["id"], "一审", "未开始"),
            )

    # 8. 更新 review_rounds.status 基于 assignments 返回情况
    all_rounds = conn.execute("SELECT id, submission_id, round_name FROM review_rounds").fetchall()
    for rr in all_rounds:
        total = conn.execute(
            "SELECT COUNT(*) FROM assignments WHERE review_round_id=?",
            (rr["id"],),
        ).fetchone()[0]
        returned = conn.execute(
            "SELECT COUNT(*) FROM assignments WHERE review_round_id=? AND returned=1",
            (rr["id"],),
        ).fetchone()[0]
        if total > 0 and returned >= total:
            conn.execute(
                "UPDATE review_rounds SET status='待主编决定' WHERE id=? AND status NOT IN ('已完成','待回复作者')",
                (rr["id"],),
            )

    conn.commit()
    print("  回填完成。")


if __name__ == "__main__":
    backup()
    migrate()
