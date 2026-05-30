"""
v7 数据库迁移 — 回填 review_rounds 使与 submissions.workflow_stage 一致

幂等，可重复运行。
用法: python3 migrate_v7_workflow_reconcile.py
"""
import sqlite3
import os
import shutil

DB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DB_DIR, "journal.db")
BACKUP_PATH = os.path.join(DB_DIR, "journal.db.bak.v7")


def backup():
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"[备份] {DB_PATH} -> {BACKUP_PATH}")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate():
    conn = get_conn()

    # ── 1. 映射旧轮次名 → 新轮次名 ──
    old_round_map = {"再审": "三审", "终审": "三审"}
    for old, new in old_round_map.items():
        cnt = conn.execute(
            "UPDATE review_rounds SET round_name=? WHERE round_name=?",
            (new, old),
        ).rowcount
        if cnt:
            print(f"  轮次名映射: {old} -> {new} ({cnt} 条)")
        conn.execute(
            "UPDATE assignments SET round=? WHERE round=?",
            (new, old),
        )

    # ── 2. 根据 submissions.workflow_stage 回填 review_rounds ──
    subs = conn.execute(
        "SELECT id, workflow_stage, current_round, status, final_decision FROM submissions"
    ).fetchall()

    for s in subs:
        sid = s["id"]
        wf = (s["workflow_stage"] or "").strip()
        cur_round = (s["current_round"] or "一审").strip()
        coarse = (s["status"] or "").strip()

        # 退稿稿件：回填 chief_decision + author_reply_status
        if wf == "已退稿" or coarse == "已退稿":
            for rn in ["一审", "二审", "三审"]:
                rr = conn.execute(
                    "SELECT id, chief_decision, author_reply_status FROM review_rounds WHERE submission_id=? AND round_name=?",
                    (sid, rn),
                ).fetchone()
                if rr:
                    if not rr["chief_decision"]:
                        conn.execute(
                            "UPDATE review_rounds SET chief_decision='退稿', status='已完成', author_reply_status='已发送', updated_at=datetime('now','localtime') WHERE id=?",
                            (rr["id"],),
                        )
            conn.execute(
                "UPDATE submissions SET final_decision='退稿' WHERE id=? AND (final_decision IS NULL OR final_decision='')",
                (sid,),
            )

        # 已录用稿件
        elif wf == "已通过三审" or coarse == "已录用":
            for rn in ["一审", "二审", "三审"]:
                rr = conn.execute(
                    "SELECT id, chief_decision, status FROM review_rounds WHERE submission_id=? AND round_name=?",
                    (sid, rn),
                ).fetchone()
                if rr:
                    if rn == "三审" and not rr["chief_decision"]:
                        conn.execute(
                            "UPDATE review_rounds SET chief_decision='通过', status='已完成', updated_at=datetime('now','localtime') WHERE id=?",
                            (rr["id"],),
                        )
                    elif rn != "三审" and rr["status"] == "待主编决定":
                        conn.execute(
                            "UPDATE review_rounds SET chief_decision='通过', status='已完成', updated_at=datetime('now','localtime') WHERE id=?",
                            (rr["id"],),
                        )
            conn.execute(
                "UPDATE submissions SET final_decision='通过', current_round='三审' WHERE id=? AND (final_decision IS NULL OR final_decision='')",
                (sid,),
            )

        # 待作者返修
        elif wf == "待作者返修":
            rr = conn.execute(
                "SELECT id, chief_decision, author_reply_status FROM review_rounds WHERE submission_id=? AND round_name=?",
                (sid, cur_round),
            ).fetchone()
            if rr:
                if not rr["chief_decision"]:
                    conn.execute(
                        "UPDATE review_rounds SET chief_decision='返修', status='待作者返修', author_reply_status='已发送', updated_at=datetime('now','localtime') WHERE id=?",
                        (rr["id"],),
                    )

        # 作者撤稿
        elif wf == "作者撤稿" or coarse == "作者撤稿":
            conn.execute(
                "UPDATE submissions SET final_decision='撤稿' WHERE id=? AND (final_decision IS NULL OR final_decision='')",
                (sid,),
            )

    conn.commit()

    # ── 3. 为有 assignment 但无 review_rounds 的稿件补建轮次 ──
    orphan_assigns = conn.execute("""
        SELECT DISTINCT a.submission_id, a.round
        FROM assignments a
        LEFT JOIN review_rounds rr ON rr.submission_id = a.submission_id AND rr.round_name = a.round
        WHERE rr.id IS NULL
    """).fetchall()
    for oa in orphan_assigns:
        conn.execute(
            "INSERT INTO review_rounds (submission_id, round_name, status) VALUES (?,?,?)",
            (oa["submission_id"], oa["round"], "未开始"),
        )
        print(f"  补建轮次: submission {oa['submission_id']} round {oa['round']}")

    # ── 4. 确保 assignments.review_round_id 不为空 ──
    null_rr = conn.execute("""
        UPDATE assignments SET review_round_id = (
            SELECT rr.id FROM review_rounds rr
            WHERE rr.submission_id = assignments.submission_id AND rr.round_name = assignments.round
            LIMIT 1
        )
        WHERE review_round_id IS NULL
    """).rowcount
    if null_rr:
        print(f"  回填 review_round_id: {null_rr} 条")

    conn.commit()
    conn.close()
    print("v7 迁移完成。")


if __name__ == "__main__":
    backup()
    migrate()
