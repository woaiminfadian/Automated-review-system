"""
学报数据库管理工具
用法: python3 journal_cli.py
"""
import sqlite3, os, json, sys
from datetime import datetime, date

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "journal.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def fmt(r):
    return dict(r)


# ── 作者 ──────────────────────────────────────────

def add_author(conn):
    print("\n=== 录入投稿人信息 ===")
    name = input("姓名: ").strip()
    if not name:
        return
    email = input("邮箱: ").strip()
    phone = input("电话: ").strip()
    affiliation = input("学校/单位: ").strip()
    department = input("院系: ").strip()
    grade = input("身份(硕士/博士/教师等): ").strip()
    address = input("通讯地址: ").strip()
    cur = conn.execute(
        "INSERT INTO authors (name,email,phone,affiliation,department,grade,address) VALUES (?,?,?,?,?,?,?)",
        (name, email, phone, affiliation, department, grade, address),
    )
    conn.commit()
    aid = cur.lastrowid
    print(f"✓ 作者已录入，ID={aid}")


def list_authors(conn):
    rows = conn.execute(
        "SELECT id, name, affiliation, grade, email, phone FROM authors ORDER BY id DESC LIMIT 30"
    ).fetchall()
    if not rows:
        print("  暂无作者记录")
        return
    print(f"\n{'ID':<4} {'姓名':<10} {'单位':<24} {'身份':<14} {'邮箱':<28} {'电话':<14}")
    print("-" * 94)
    for r in rows:
        print(
            f"{r['id']:<4} {r['name']:<10} {(r['affiliation'] or ''):<24} {(r['grade'] or ''):<14} {(r['email'] or ''):<28} {(r['phone'] or ''):<14}"
        )


def search_authors(conn):
    kw = input("搜索关键词（姓名/单位/邮箱）: ").strip()
    rows = conn.execute(
        "SELECT id, name, affiliation, grade, email, phone FROM authors WHERE name LIKE ? OR affiliation LIKE ? OR email LIKE ? ORDER BY id DESC",
        (f"%{kw}%", f"%{kw}%", f"%{kw}%"),
    ).fetchall()
    if not rows:
        print("  未找到匹配的作者")
        return
    print(f"\n{'ID':<4} {'姓名':<10} {'单位':<24} {'身份':<14} {'邮箱':<28} {'电话':<14}")
    print("-" * 94)
    for r in rows:
        print(
            f"{r['id']:<4} {r['name']:<10} {(r['affiliation'] or ''):<24} {(r['grade'] or ''):<14} {(r['email'] or ''):<28} {(r['phone'] or ''):<14}"
        )


# ── 稿件 ──────────────────────────────────────────

FIELDS = [
    "民法", "商法", "知识产权法", "经济法", "数据法",
    "民事诉讼法", "国际法", "刑法", "刑事诉讼法",
    "法理学", "宪法与行政法", "环境法", "劳动法",
    "法律史", "其他",
]

STATUSES = ["待处理", "派稿中", "审稿中", "返修中", "已录用", "已退稿", "作者撤稿"]


def add_submission(conn):
    print("\n=== 录入新稿件 ===")
    title = input("稿件标题: ").strip()
    if not title:
        return
    print("学科方向:")
    for i, f in enumerate(FIELDS, 1):
        print(f"  {i}. {f}")
    try:
        fi = int(input("选择(序号): ").strip())
        field = FIELDS[fi - 1]
    except (ValueError, IndexError):
        field = input("手动输入学科方向: ").strip()
    stype = input("来稿性质(正常来稿/专栏来稿/协助审稿)[默认正常来稿]: ").strip() or "正常来稿"
    rdate = input("收稿日期(YYYY.MM.DD)[默认今天]: ").strip() or datetime.now().strftime("%Y.%m.%d")

    aid1 = None
    print("\n--- 第一作者 ---")
    q = input("从已有作者中选择？(y/n,默认y): ").strip().lower()
    if q != "n":
        list_authors(conn)
        try:
            aid1 = int(input("选择作者ID(直接回车新建): ").strip())
            conn.execute("SELECT 1 FROM authors WHERE id=?", (aid1,)).fetchone()
        except:
            aid1 = None
    if not aid1:
        aid1 = add_author_inline(conn)

    aid2 = None
    q2 = input("\n有第二作者？(y/n): ").strip().lower()
    if q2 == "y":
        qq = input("从已有作者中选择？(y/n,默认y): ").strip().lower()
        if qq != "n":
            list_authors(conn)
            try:
                aid2 = int(input("选择作者ID(直接回车新建): ").strip())
                conn.execute("SELECT 1 FROM authors WHERE id=?", (aid2,)).fetchone()
            except:
                aid2 = None
        if not aid2:
            aid2 = add_author_inline(conn)

    cur = conn.execute(
        "INSERT INTO submissions (title,field,submission_type,author1_id,author2_id,received_date,status) VALUES (?,?,?,?,?,?,?)",
        (title, field, stype, aid1, aid2, rdate, "待处理"),
    )
    conn.commit()
    sid = cur.lastrowid
    print(f"\n✓ 稿件已录入，ID={sid}")
    return sid


def add_author_inline(conn):
    print("--- 新建作者 ---")
    name = input("  姓名: ").strip()
    email = input("  邮箱: ").strip()
    phone = input("  电话: ").strip()
    affiliation = input("  学校/单位: ").strip()
    grade = input("  身份: ").strip()
    address = input("  通讯地址: ").strip()
    cur = conn.execute(
        "INSERT INTO authors (name,email,phone,affiliation,grade,address) VALUES (?,?,?,?,?,?)",
        (name, email, phone, affiliation, grade, address),
    )
    conn.commit()
    return cur.lastrowid


def list_submissions(conn, status_filter=None):
    sql = """
        SELECT s.id, s.title, s.field, s.received_date, s.status,
               a1.name AS author1, a2.name AS author2
        FROM submissions s
        LEFT JOIN authors a1 ON s.author1_id = a1.id
        LEFT JOIN authors a2 ON s.author2_id = a2.id
    """
    params = []
    if status_filter:
        sql += " WHERE s.status = ?"
        params.append(status_filter)
    sql += " ORDER BY s.id DESC"
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        print("  暂无稿件记录")
        return
    print(
        f"\n{'ID':<4} {'状态':<8} {'学科':<12} {'日期':<12} {'第一作者':<12} {'第二作者':<12} {'标题':<40}"
    )
    print("-" * 100)
    for r in rows:
        t = r["title"] if len(r["title"]) <= 38 else r["title"][:37] + "…"
        print(
            f"{r['id']:<4} {r['status']:<8} {r['field']:<12} {r['received_date']:<12} {(r['author1'] or ''):<12} {(r['author2'] or ''):<12} {t}"
        )


def view_submission(conn, sid):
    r = conn.execute(
        """SELECT s.*, a1.name AS a1_name, a1.affiliation AS a1_aff, a1.grade AS a1_grade,
                  a1.email AS a1_email, a1.phone AS a1_phone, a1.address AS a1_addr,
                  a2.name AS a2_name, a2.affiliation AS a2_aff, a2.grade AS a2_grade
           FROM submissions s
           LEFT JOIN authors a1 ON s.author1_id = a1.id
           LEFT JOIN authors a2 ON s.author2_id = a2.id
           WHERE s.id = ?""",
        (sid,),
    ).fetchone()
    if not r:
        print("  未找到该稿件")
        return
    print(f"\n{'='*60}")
    print(f"  稿件 ID: {r['id']}")
    print(f"  标题: {r['title']}")
    print(f"  学科方向: {r['field']}")
    print(f"  来稿性质: {r['submission_type']}")
    print(f"  收稿日期: {r['received_date']}")
    print(f"  状态: {r['status']}")
    print(f"  排期: {r['issue'] or '未安排'}")
    print(f"  备注: {r['notes'] or '-'}")
    print(f"\n  ── 第一作者 ──")
    print(f"    姓名: {r['a1_name']}")
    print(f"    单位: {r['a1_aff'] or '-'}")
    print(f"    身份: {r['a1_grade'] or '-'}")
    print(f"    邮箱: {r['a1_email'] or '-'}")
    print(f"    电话: {r['a1_phone'] or '-'}")
    print(f"    地址: {r['a1_addr'] or '-'}")
    if r["a2_name"]:
        print(f"\n  ── 第二作者 ──")
        print(f"    姓名: {r['a2_name']}")
        print(f"    单位: {r['a2_aff'] or '-'}")
        print(f"    身份: {r['a2_grade'] or '-'}")

    # 派稿历史
    assigns = conn.execute(
        """SELECT a.*, e.name AS editor_name
           FROM assignments a JOIN editors e ON a.editor_id = e.id
           WHERE a.submission_id = ? ORDER BY a.round, a.assigned_date""",
        (sid,),
    ).fetchall()
    if assigns:
        print(f"\n  ── 派稿记录 ({len(assigns)}条) ──")
        print(f"  {'轮次':<8} {'编辑':<10} {'派稿日期':<12} {'状态':<10} {'结果':<10}")
        print(f"  {'-'*50}")
        for a in assigns:
            print(
                f"  {a['round']:<8} {a['editor_name']:<10} {a['assigned_date']:<12} {a['status']:<10} {(a['result'] or '-'):<10}"
            )
    print(f"{'='*60}")


def search_submissions(conn):
    print("\n搜索条件（留空跳过）:")
    kw = input("标题/作者关键词: ").strip()
    field = input("学科方向(回车全部): ").strip()
    status = input("状态(回车全部): ").strip()

    sql = """
        SELECT s.id, s.title, s.field, s.received_date, s.status,
               a1.name AS author1
        FROM submissions s
        LEFT JOIN authors a1 ON s.author1_id = a1.id
        WHERE 1=1
    """
    params = []
    if kw:
        sql += " AND (s.title LIKE ? OR a1.name LIKE ?)"
        params.extend([f"%{kw}%", f"%{kw}%"])
    if field:
        sql += " AND s.field = ?"
        params.append(field)
    if status:
        sql += " AND s.status = ?"
        params.append(status)
    sql += " ORDER BY s.id DESC"
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        print("  未找到匹配稿件")
        return
    print(f"\n{'ID':<4} {'状态':<8} {'学科':<10} {'日期':<12} {'作者':<12} {'标题':<46}")
    print("-" * 92)
    for r in rows:
        t = r["title"] if len(r["title"]) <= 44 else r["title"][:43] + "…"
        print(
            f"{r['id']:<4} {r['status']:<8} {r['field']:<10} {r['received_date']:<12} {(r['author1'] or ''):<12} {t}"
        )


def update_submission_status(conn):
    sid = input("稿件ID: ").strip()
    if not sid.isdigit():
        return
    r = conn.execute("SELECT id, title, status FROM submissions WHERE id=?", (sid,)).fetchone()
    if not r:
        print("未找到该稿件")
        return
    print(f"当前状态: {r['status']}")
    print("可选状态:")
    for i, s in enumerate(STATUSES, 1):
        print(f"  {i}. {s}")
    try:
        ci = int(input("选择新状态(序号): ").strip())
        new_status = STATUSES[ci - 1]
    except (ValueError, IndexError):
        new_status = input("手动输入状态: ").strip()
    conn.execute("UPDATE submissions SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
                 (new_status, sid))
    conn.commit()
    print(f"✓ 稿件 {sid} 状态已更新为: {new_status}")


# ── 编辑 ──────────────────────────────────────────

def list_editors(conn):
    rows = conn.execute(
        "SELECT id, name, email, role, subjects, active FROM editors ORDER BY subjects, name"
    ).fetchall()
    if not rows:
        print("  暂无编辑记录")
        return
    print(f"\n{'ID':<4} {'姓名':<10} {'角色':<8} {'邮箱':<28} {'负责领域':<20} {'状态':<4}")
    print("-" * 74)
    for r in rows:
        subs = ""
        if r["subjects"]:
            try:
                subs = ", ".join(json.loads(r["subjects"]))
            except:
                subs = r["subjects"]
        active = "✓" if r["active"] else "✗"
        print(
            f"{r['id']:<4} {r['name']:<10} {r['role']:<8} {(r['email'] or ''):<28} {subs:<20} {active}"
        )


def add_editor(conn):
    print("\n=== 添加编辑 ===")
    name = input("姓名: ").strip()
    if not name:
        return
    email = input("邮箱: ").strip()
    subjects = input("负责领域(逗号分隔,如 民法,商法): ").strip()
    subjects_json = json.dumps([s.strip() for s in subjects.split(",") if s.strip()], ensure_ascii=False) if subjects else "[]"
    try:
        conn.execute(
            "INSERT INTO editors (name, email, subjects) VALUES (?,?,?)",
            (name, email, subjects_json),
        )
        conn.commit()
        print(f"✓ 编辑 {name} 已添加")
    except sqlite3.IntegrityError:
        print("  该编辑已存在")


# ── 派稿 ──────────────────────────────────────────

ROUNDS = ["一审", "二审", "再审", "终审", "外审"]
ASSIGN_STATUSES = ["待审", "审稿中", "已返回", "已通过", "返修", "退稿", "待确认"]


def assign_paper(conn):
    print("\n=== 派稿 ===")
    # 列出待处理稿件
    pending = conn.execute(
        """SELECT s.id, s.title, s.field, a.name AS author1
           FROM submissions s
           LEFT JOIN authors a ON s.author1_id = a.id
           WHERE s.status IN ('待处理','派稿中','审稿中','返修中')
           ORDER BY s.id DESC"""
    ).fetchall()
    if not pending:
        print("  暂无可派稿件")
        return
    print("\n可派稿件:")
    print(f"{'ID':<4} {'学科':<10} {'作者':<12} {'标题':<50}")
    print("-" * 76)
    for r in pending:
        t = r["title"] if len(r["title"]) <= 48 else r["title"][:47] + "…"
        print(f"{r['id']:<4} {r['field']:<10} {(r['author1'] or ''):<12} {t}")

    sid = input("\n选择稿件ID: ").strip()
    if not sid.isdigit():
        return
    r = conn.execute("SELECT id, title, field, status FROM submissions WHERE id=?", (sid,)).fetchone()
    if not r:
        print("无效ID")
        return

    print(f"\n稿件: {r['title']}")
    print(f"学科: {r['field']}")

    # 显示该学科可派的编辑
    subs_editors = conn.execute(
        "SELECT id, name, email FROM editors WHERE active=1 AND subjects LIKE ? ORDER BY name",
        (f"%{r['field']}%",),
    ).fetchall()
    if not subs_editors:
        subs_editors = conn.execute(
            "SELECT id, name, email FROM editors WHERE active=1 ORDER BY name"
        ).fetchall()
    print("\n可用编辑:")
    print(f"{'ID':<4} {'姓名':<12} {'邮箱':<28}")
    print("-" * 44)
    for e in subs_editors:
        print(f"{e['id']:<4} {e['name']:<12} {(e['email'] or ''):<28}")
        # 也可以显示更多编辑
    all_eds = conn.execute("SELECT id, name FROM editors WHERE active=1 ORDER BY name").fetchall()
    if len(all_eds) > len(subs_editors):
        print(f"\n其他编辑（共{len(all_eds)}位）可用，输入ID即可选择任意编辑")

    eid = input("选择编辑ID: ").strip()
    if not eid.isdigit():
        return
    editor = conn.execute("SELECT name FROM editors WHERE id=?", (eid,)).fetchone()
    if not editor:
        print("无效编辑ID")
        return

    print("审稿轮次:")
    for i, rn in enumerate(ROUNDS, 1):
        print(f"  {i}. {rn}")
    try:
        ri = int(input("选择(序号)[默认1]: ").strip() or "1")
        round_name = ROUNDS[ri - 1]
    except (ValueError, IndexError):
        round_name = "一审"

    adate = input(f"派稿日期(YYYY.MM.DD)[默认今天]: ").strip() or datetime.now().strftime("%Y.%m.%d")

    cur = conn.execute(
        "INSERT INTO assignments (submission_id, editor_id, round, assigned_date, status) VALUES (?,?,?,?,?)",
        (sid, eid, round_name, adate, "待审"),
    )
    # 更新稿件状态
    if r["status"] == "待处理":
        conn.execute(
            "UPDATE submissions SET status='派稿中', updated_at=datetime('now','localtime') WHERE id=?",
            (sid,),
        )
    conn.commit()
    aid = cur.lastrowid
    print(f"\n✓ 派稿完成！记录ID={aid}")
    print(f"  {editor['name']} 负责 {round_name}，稿件ID={sid}")


def list_assignments(conn):
    print("\n筛选（留空全部）:")
    round_f = input("轮次(一审/二审/再审/终审): ").strip()
    status_f = input("状态(待审/审稿中/已返回/返修/退稿/已通过): ").strip()
    editor_f = input("编辑姓名: ").strip()

    sql = """
        SELECT a.id, a.round, a.status, a.result, a.assigned_date, a.result_date,
               s.id AS sid, s.title, s.field,
               e.name AS editor_name,
               au.name AS author_name
        FROM assignments a
        JOIN submissions s ON a.submission_id = s.id
        JOIN editors e ON a.editor_id = e.id
        LEFT JOIN authors au ON s.author1_id = au.id
        WHERE 1=1
    """
    params = []
    if round_f:
        sql += " AND a.round = ?"
        params.append(round_f)
    if status_f:
        sql += " AND a.status = ?"
        params.append(status_f)
    if editor_f:
        sql += " AND e.name LIKE ?"
        params.append(f"%{editor_f}%")
    sql += " ORDER BY a.id DESC LIMIT 40"

    rows = conn.execute(sql, params).fetchall()
    if not rows:
        print("  暂无派稿记录")
        return
    print(
        f"\n{'ID派':<5} {'轮次':<6} {'状态':<8} {'结果':<8} {'派稿日':<11} {'编辑':<10} {'作者':<10} {'标题':<42}"
    )
    print("-" * 100)
    for r in rows:
        t = r["title"] if len(r["title"]) <= 40 else r["title"][:39] + "…"
        print(
            f"{r['id']:<5} {r['round']:<6} {r['status']:<8} {(r['result'] or '-'):<8} {r['assigned_date']:<11} {r['editor_name']:<10} {(r['author_name'] or ''):<10} {t}"
        )


def update_assignment(conn):
    aid = input("派稿记录ID: ").strip()
    if not aid.isdigit():
        return
    r = conn.execute(
        """SELECT a.*, e.name AS editor_name, s.title
           FROM assignments a
           JOIN editors e ON a.editor_id = e.id
           JOIN submissions s ON a.submission_id = s.id
           WHERE a.id=?""",
        (aid,),
    ).fetchone()
    if not r:
        print("未找到该派稿记录")
        return
    print(f"\n稿件: {r['title']}")
    print(f"编辑: {r['editor_name']} | 轮次: {r['round']}")
    print(f"当前状态: {r['status']} | 当前结果: {r['result'] or '无'}")

    print("\n更新状态:")
    for i, s in enumerate(ASSIGN_STATUSES, 1):
        print(f"  {i}. {s}")
    try:
        ci = int(input("选择新状态(序号): ").strip())
        new_status = ASSIGN_STATUSES[ci - 1]
    except (ValueError, IndexError):
        new_status = input("手动输入状态: ").strip()

    new_result = ""
    if new_status in ("已通过", "返修", "退稿"):
        print(f"\n结果({new_status}对应的结果):")
        if new_status == "已通过":
            new_result = "通过"
        elif new_status == "返修":
            new_result = "返修"
        elif new_status == "退稿":
            new_result = "退稿"
        else:
            new_result = input("输入结果: ").strip()

    rdate = input("结果日期(YYYY.MM.DD)[默认今天]: ").strip() or datetime.now().strftime("%Y.%m.%d")
    summary = input("审稿意见摘要(可选): ").strip()

    conn.execute(
        """UPDATE assignments
           SET status=?, result=?, result_date=?, opinion_summary=?
           WHERE id=?""",
        (new_status, new_result, rdate, summary, aid),
    )
    # 同步更新稿件状态
    sid = r["submission_id"]
    if new_status == "已通过":
        conn.execute("UPDATE submissions SET status='已录用', updated_at=datetime('now','localtime') WHERE id=?", (sid,))
    elif new_status == "返修":
        conn.execute("UPDATE submissions SET status='返修中', updated_at=datetime('now','localtime') WHERE id=?", (sid,))
    elif new_status == "退稿":
        conn.execute("UPDATE submissions SET status='已退稿', updated_at=datetime('now','localtime') WHERE id=?", (sid,))
    conn.commit()
    print(f"✓ 派稿记录 {aid} 已更新")


# ── 统计 ──────────────────────────────────────────

def stats(conn):
    print("\n=== 统计概览 ===")
    total = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    by_status = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM submissions GROUP BY status ORDER BY cnt DESC"
    ).fetchall()
    by_field = conn.execute(
        "SELECT field, COUNT(*) as cnt FROM submissions GROUP BY field ORDER BY cnt DESC"
    ).fetchall()
    pending_assign = conn.execute(
        "SELECT COUNT(*) FROM assignments WHERE status='待审'"
    ).fetchone()[0]
    editors = conn.execute("SELECT COUNT(*) FROM editors WHERE active=1").fetchone()[0]
    authors = conn.execute("SELECT COUNT(*) FROM authors").fetchone()[0]

    print(f"\n  总稿件数: {total}")
    print(f"  活跃编辑: {editors}")
    print(f"  作者数:   {authors}")
    print(f"  待审派稿: {pending_assign}")
    print(f"\n  ── 稿件状态分布 ──")
    for r in by_status:
        print(f"    {r['status']}: {r['cnt']}篇")
    print(f"\n  ── 学科分布 ──")
    for r in by_field:
        print(f"    {r['field']}: {r['cnt']}篇")


# ── 主菜单 ────────────────────────────────────────

def main():
    while True:
        print("\n" + "=" * 52)
        print("  法大研究生学报 · 数据库管理系统")
        print("=" * 52)
        print("  [1]  录入新稿件")
        print("  [2]  查看全部稿件")
        print("  [3]  查看稿件详情")
        print("  [4]  搜索稿件")
        print("  [5]  修改稿件状态")
        print("  [6]  派稿")
        print("  [7]  查看派稿记录")
        print("  [8]  更新派稿结果")
        print("  [9]  管理编辑")
        print("  [10] 管理作者")
        print("  [11] 统计数据")
        print("  [0]  退出")
        print("-" * 52)
        cmd = input("选择操作: ").strip()

        conn = get_conn()
        try:
            if cmd == "1":
                add_submission(conn)
            elif cmd == "2":
                list_submissions(conn)
            elif cmd == "3":
                sid = input("稿件ID: ").strip()
                if sid.isdigit():
                    view_submission(conn, int(sid))
            elif cmd == "4":
                search_submissions(conn)
            elif cmd == "5":
                update_submission_status(conn)
            elif cmd == "6":
                assign_paper(conn)
            elif cmd == "7":
                list_assignments(conn)
            elif cmd == "8":
                update_assignment(conn)
            elif cmd == "9":
                print("\n  [a] 列出编辑  [b] 添加编辑")
                sc = input("选择: ").strip().lower()
                if sc == "a":
                    list_editors(conn)
                elif sc == "b":
                    add_editor(conn)
            elif cmd == "10":
                print("\n  [a] 列出作者  [b] 搜索作者  [c] 添加作者")
                sc = input("选择: ").strip().lower()
                if sc == "a":
                    list_authors(conn)
                elif sc == "b":
                    search_authors(conn)
                elif sc == "c":
                    add_author(conn)
            elif cmd == "11":
                stats(conn)
            elif cmd == "0":
                print("再见！")
                break
        finally:
            conn.close()


if __name__ == "__main__":
    main()
