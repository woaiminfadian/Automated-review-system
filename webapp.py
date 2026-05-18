"""
学报数据库 Web 管理界面
用法: python3 webapp.py
"""
import sqlite3, os, json, sys
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "journal.db")

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

FIELDS = [
    "民法", "商法", "知识产权法", "经济法", "数据法",
    "民事诉讼法", "国际法", "刑法", "刑事诉讼法",
    "法理学", "宪法与行政法", "环境法", "劳动法",
    "法律史", "其他",
]
STATUSES = ["待处理", "派稿中", "审稿中", "返修中", "已录用", "已退稿", "作者撤稿"]
ROUNDS = ["一审", "二审", "再审", "终审", "外审"]
ASSIGN_STATUSES = ["待审", "审稿中", "已返回", "已通过", "返修", "退稿", "待确认"]

# ── 数据库 ──────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def log_activity(conn, entity_type, entity_id, action, detail=""):
    conn.execute(
        "INSERT INTO activity_log (entity_type, entity_id, action, detail) VALUES (?,?,?,?)",
        (entity_type, entity_id, action, detail),
    )

# Jinja2 自定义过滤器
@app.template_filter("json_loads")
def json_loads_filter(s):
    try:
        return json.loads(s) if s else []
    except:
        return []

# ── 首页 / 仪表盘 ──────────────────────────────────

@app.route("/")
def dashboard():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    by_status = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM submissions GROUP BY status ORDER BY cnt DESC"
    ).fetchall()
    by_field = conn.execute(
        "SELECT field, COUNT(*) as cnt FROM submissions GROUP BY field ORDER BY cnt DESC"
    ).fetchall()
    editor_count = conn.execute("SELECT COUNT(*) FROM editors WHERE active=1").fetchone()[0]
    author_count = conn.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
    pending_assign = conn.execute("SELECT COUNT(*) FROM assignments WHERE status='待审'").fetchone()[0]
    recent_activity = conn.execute(
        "SELECT * FROM activity_log ORDER BY id DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return render_template("dashboard.html", total=total, by_status=by_status, by_field=by_field,
                           editor_count=editor_count, author_count=author_count,
                           pending_assign=pending_assign, recent_activity=recent_activity)

# ── 稿件管理 ────────────────────────────────────────

@app.route("/submissions")
def submissions_list():
    conn = get_conn()
    status_f = request.args.get("status", "")
    field_f = request.args.get("field", "")
    kw = request.args.get("kw", "")
    sql = """
        SELECT s.id, s.title, s.field, s.received_date, s.status, s.submission_type,
               a1.name AS author1, a2.name AS author2
        FROM submissions s
        LEFT JOIN authors a1 ON s.author1_id = a1.id
        LEFT JOIN authors a2 ON s.author2_id = a2.id
        WHERE 1=1
    """
    params = []
    if status_f:
        sql += " AND s.status = ?"
        params.append(status_f)
    if field_f:
        sql += " AND s.field = ?"
        params.append(field_f)
    if kw:
        sql += " AND (s.title LIKE ? OR a1.name LIKE ?)"
        params.extend([f"%{kw}%", f"%{kw}%"])
    sql += " ORDER BY s.id DESC"
    submissions = conn.execute(sql, params).fetchall()

    # 批量查询审稿进度
    ids = [s["id"] for s in submissions]
    progress_map = {}
    if ids:
        placeholders = ",".join("?" * len(ids))
        assigns = conn.execute(f"""
            SELECT a.submission_id, a.round, a.status, a.result,
                   e.name AS editor_name
            FROM assignments a
            JOIN editors e ON a.editor_id = e.id
            WHERE a.submission_id IN ({placeholders})
            ORDER BY a.submission_id, a.round, a.assigned_date
        """, ids).fetchall()
        for a in assigns:
            sid = a["submission_id"]
            if sid not in progress_map:
                progress_map[sid] = []
            progress_map[sid].append({
                "round": a["round"],
                "status": a["status"],
                "result": a["result"],
                "editor": a["editor_name"],
            })
    conn.close()

    sub_list = []
    for s in submissions:
        d = dict(s)
        raw = progress_map.get(s["id"], [])
        d["progress_by_round"] = {p["round"]: p for p in raw}
        d["progress_arcs"] = [p["round"] for p in raw]
        sub_list.append(d)

    return render_template("submissions.html", submissions=sub_list,
                           statuses=STATUSES, fields=FIELDS,
                           status_f=status_f, field_f=field_f, kw=kw)

@app.route("/submissions/<int:sid>")
def submission_detail(sid):
    conn = get_conn()
    sub = conn.execute("""
        SELECT s.*, a1.name AS a1_name, a1.affiliation AS a1_aff, a1.grade AS a1_grade,
               a1.email AS a1_email, a1.phone AS a1_phone, a1.address AS a1_addr,
               a2.name AS a2_name, a2.affiliation AS a2_aff, a2.grade AS a2_grade
        FROM submissions s
        LEFT JOIN authors a1 ON s.author1_id = a1.id
        LEFT JOIN authors a2 ON s.author2_id = a2.id
        WHERE s.id=?
    """, (sid,)).fetchone()
    if not sub:
        conn.close()
        flash("稿件不存在", "danger")
        return redirect(url_for("submissions_list"))
    assigns = conn.execute("""
        SELECT a.*, e.name AS editor_name, e.email AS editor_email
        FROM assignments a JOIN editors e ON a.editor_id = e.id
        WHERE a.submission_id=? ORDER BY a.round, a.assigned_date
    """, (sid,)).fetchall()
    conn.close()
    return render_template("submission_detail.html", sub=sub, assigns=assigns,
                           statuses=STATUSES, rounds=ROUNDS, assign_statuses=ASSIGN_STATUSES)

@app.route("/submissions/add", methods=["GET", "POST"])
def submission_add():
    conn = get_conn()
    authors = conn.execute("SELECT id, name, affiliation FROM authors ORDER BY name").fetchall()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        field = request.form.get("field", "").strip()
        if not title or not field:
            flash("请填写标题和学科方向", "danger")
            conn.close()
            return render_template("submission_add.html", fields=FIELDS, authors=authors,
                                   statuses=STATUSES)
        sub_type = request.form.get("submission_type", "正常来稿")
        rdate = request.form.get("received_date", "").strip() or datetime.now().strftime("%Y.%m.%d")
        status = request.form.get("status", "待处理")

        # 作者1
        aid1 = None
        a1_select = request.form.get("author1_select", "")
        if a1_select == "existing":
            aid1 = request.form.get("author1_id", "")
            aid1 = int(aid1) if aid1.isdigit() else None
        elif a1_select == "new":
            name1 = request.form.get("author1_name", "").strip()
            if name1:
                cur = conn.execute(
                    "INSERT INTO authors (name, email, phone, affiliation, grade) VALUES (?,?,?,?,?)",
                    (name1, request.form.get("author1_email", "").strip(),
                     request.form.get("author1_phone", "").strip(),
                     request.form.get("author1_affiliation", "").strip(),
                     request.form.get("author1_grade", "").strip()),
                )
                aid1 = cur.lastrowid

        # 作者2
        aid2 = None
        if request.form.get("has_author2") == "yes":
            a2_select = request.form.get("author2_select", "existing")
            if a2_select == "existing":
                aid2 = request.form.get("author2_id", "")
                aid2 = int(aid2) if aid2.isdigit() else None
            elif a2_select == "new":
                name2 = request.form.get("author2_name", "").strip()
                if name2:
                    cur = conn.execute(
                        "INSERT INTO authors (name, email, phone, affiliation, grade) VALUES (?,?,?,?,?)",
                        (name2, request.form.get("author2_email", "").strip(),
                         request.form.get("author2_phone", "").strip(),
                         request.form.get("author2_affiliation", "").strip(),
                         request.form.get("author2_grade", "").strip()),
                    )
                    aid2 = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO submissions (title, field, submission_type, author1_id, author2_id, received_date, status) VALUES (?,?,?,?,?,?,?)",
            (title, field, sub_type, aid1, aid2, rdate, status),
        )
        sid = cur.lastrowid
        log_activity(conn, "submission", sid, "录入稿件", f"标题: {title}")
        conn.commit()
        conn.close()
        flash(f"稿件已录入，ID={sid}", "success")
        return redirect(url_for("submission_detail", sid=sid))

    conn.close()
    return render_template("submission_add.html", fields=FIELDS, authors=authors, statuses=STATUSES)

@app.route("/submissions/<int:sid>/status", methods=["POST"])
def submission_update_status(sid):
    new_status = request.form.get("status", "")
    if new_status not in STATUSES:
        flash("无效状态", "danger")
        return redirect(url_for("submission_detail", sid=sid))
    conn = get_conn()
    conn.execute("UPDATE submissions SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
                 (new_status, sid))
    log_activity(conn, "submission", sid, "更新状态", f"状态: {new_status}")
    conn.commit()
    conn.close()
    flash(f"稿件 {sid} 状态已更新为: {new_status}", "success")
    return redirect(url_for("submission_detail", sid=sid))

@app.route("/submissions/<int:sid>/edit", methods=["GET", "POST"])
def submission_edit(sid):
    conn = get_conn()
    sub = conn.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
    if not sub:
        conn.close()
        flash("稿件不存在", "danger")
        return redirect(url_for("submissions_list"))
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        field = request.form.get("field", "").strip()
        sub_type = request.form.get("submission_type", "正常来稿")
        rdate = request.form.get("received_date", "").strip()
        notes = request.form.get("notes", "").strip()
        issue = request.form.get("issue", "").strip()
        status = request.form.get("status", "").strip()
        if title and field:
            conn.execute(
                "UPDATE submissions SET title=?, field=?, submission_type=?, received_date=?, status=?, issue=?, notes=?, updated_at=datetime('now','localtime') WHERE id=?",
                (title, field, sub_type, rdate, status, issue, notes, sid),
            )
            log_activity(conn, "submission", sid, "编辑稿件", f"标题: {title}")
            conn.commit()
            conn.close()
            flash("稿件已更新", "success")
            return redirect(url_for("submission_detail", sid=sid))
        flash("请填写标题和学科方向", "danger")
    authors = conn.execute("SELECT id, name, affiliation FROM authors ORDER BY name").fetchall()
    conn.close()
    return render_template("submission_edit.html", sub=sub, fields=FIELDS, statuses=STATUSES, authors=authors)

@app.route("/submissions/<int:sid>/delete", methods=["POST"])
def submission_delete(sid):
    conn = get_conn()
    conn.execute("DELETE FROM assignments WHERE submission_id=?", (sid,))
    conn.execute("DELETE FROM submissions WHERE id=?", (sid,))
    log_activity(conn, "submission", sid, "删除稿件", "")
    conn.commit()
    conn.close()
    flash("稿件已删除", "success")
    return redirect(url_for("submissions_list"))

# ── 派稿管理 ────────────────────────────────────────

@app.route("/assignments")
def assignments_list():
    conn = get_conn()
    round_f = request.args.get("round", "")
    status_f = request.args.get("status", "")
    editor_f = request.args.get("editor", "")

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
    sql += " ORDER BY a.id DESC LIMIT 100"
    assignments = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("assignments.html", assignments=assignments,
                           rounds=ROUNDS, assign_statuses=ASSIGN_STATUSES,
                           round_f=round_f, status_f=status_f, editor_f=editor_f)

@app.route("/assignments/add", methods=["GET", "POST"])
def assignment_add():
    conn = get_conn()
    if request.method == "POST":
        sid = request.form.get("submission_id", "").strip()
        eid = request.form.get("editor_id", "").strip()
        round_name = request.form.get("round", "一审")
        adate = request.form.get("assigned_date", "").strip() or datetime.now().strftime("%Y.%m.%d")
        if not sid or not eid:
            flash("请选择稿件和编辑", "danger")
            conn.close()
            return redirect(url_for("assignment_add"))
        conn.execute(
            "INSERT INTO assignments (submission_id, editor_id, round, assigned_date, status) VALUES (?,?,?,?,?)",
            (sid, eid, round_name, adate, "待审"),
        )
        sub = conn.execute("SELECT status FROM submissions WHERE id=?", (sid,)).fetchone()
        if sub and sub["status"] == "待处理":
            conn.execute("UPDATE submissions SET status='派稿中', updated_at=datetime('now','localtime') WHERE id=?", (sid,))
        editor = conn.execute("SELECT name FROM editors WHERE id=?", (eid,)).fetchone()
        log_activity(conn, "assignment", sid, "派稿", f"编辑: {editor['name']}, 轮次: {round_name}")
        conn.commit()
        conn.close()
        flash("派稿成功", "success")
        return redirect(url_for("assignments_list"))

    pend = conn.execute("""
        SELECT s.id, s.title, s.field, a.name AS author1
        FROM submissions s
        LEFT JOIN authors a ON s.author1_id = a.id
        WHERE s.status IN ('待处理','派稿中','审稿中','返修中')
        ORDER BY s.id DESC
    """).fetchall()
    editors = conn.execute("SELECT id, name, email, subjects FROM editors WHERE active=1 ORDER BY name").fetchall()
    conn.close()
    return render_template("assignment_add.html", pend=pend, editors=editors, rounds=ROUNDS)

@app.route("/assignments/<int:aid>/update", methods=["POST"])
def assignment_update(aid):
    conn = get_conn()
    r = conn.execute("""
        SELECT a.*, e.name AS editor_name, s.title
        FROM assignments a
        JOIN editors e ON a.editor_id = e.id
        JOIN submissions s ON a.submission_id = s.id
        WHERE a.id=?
    """, (aid,)).fetchone()
    if not r:
        conn.close()
        flash("派稿记录不存在", "danger")
        return redirect(url_for("assignments_list"))

    new_status = request.form.get("status", "").strip()
    new_result = request.form.get("result", "").strip()
    rdate = request.form.get("result_date", "").strip() or datetime.now().strftime("%Y.%m.%d")
    summary = request.form.get("opinion_summary", "").strip()

    conn.execute(
        "UPDATE assignments SET status=?, result=?, result_date=?, opinion_summary=? WHERE id=?",
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
    log_activity(conn, "assignment", aid, "更新派稿结果", f"状态: {new_status}, 结果: {new_result}")
    conn.commit()
    conn.close()
    flash(f"派稿记录 {aid} 已更新", "success")
    return redirect(url_for("assignments_list"))

# ── 作者管理 ────────────────────────────────────────

@app.route("/authors")
def authors_list():
    conn = get_conn()
    kw = request.args.get("kw", "")
    if kw:
        rows = conn.execute(
            "SELECT id, name, affiliation, grade, email, phone, department FROM authors WHERE name LIKE ? OR affiliation LIKE ? OR email LIKE ? ORDER BY id DESC LIMIT 50",
            (f"%{kw}%", f"%{kw}%", f"%{kw}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, affiliation, grade, email, phone, department FROM authors ORDER BY id DESC LIMIT 50"
        ).fetchall()
    conn.close()
    return render_template("authors.html", authors=rows, kw=kw)

@app.route("/authors/add", methods=["POST"])
def author_add():
    name = request.form.get("name", "").strip()
    if not name:
        flash("请填写姓名", "danger")
        return redirect(url_for("authors_list"))
    conn = get_conn()
    conn.execute(
        "INSERT INTO authors (name, email, phone, affiliation, department, grade, address) VALUES (?,?,?,?,?,?,?)",
        (name, request.form.get("email", "").strip(), request.form.get("phone", "").strip(),
         request.form.get("affiliation", "").strip(), request.form.get("department", "").strip(),
         request.form.get("grade", "").strip(), request.form.get("address", "").strip()),
    )
    conn.commit()
    log_activity(conn, "author", conn.execute("SELECT last_insert_rowid()").fetchone()[0], "录入作者", f"姓名: {name}")
    conn.close()
    flash(f"作者 {name} 已录入", "success")
    return redirect(url_for("authors_list"))

@app.route("/authors/<int:aid>/delete", methods=["POST"])
def author_delete(aid):
    conn = get_conn()
    conn.execute("UPDATE authors SET name=name || '(已删除)' WHERE id=?", (aid,))
    log_activity(conn, "author", aid, "删除作者", "")
    conn.commit()
    conn.close()
    flash("作者已移除", "success")
    return redirect(url_for("authors_list"))

# ── 编辑管理 ────────────────────────────────────────

@app.route("/editors")
def editors_list():
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, name, email, role, subjects, active FROM editors ORDER BY active DESC, subjects, name"
    ).fetchall()]
    for r in rows:
        if r["subjects"]:
            try:
                r["subjects_list"] = json.loads(r["subjects"])
            except:
                r["subjects_list"] = [r["subjects"]]
        else:
            r["subjects_list"] = []
    conn.close()
    return render_template("editors.html", editors=rows)

@app.route("/editors/add", methods=["POST"])
def editor_add():
    name = request.form.get("name", "").strip()
    if not name:
        flash("请填写姓名", "danger")
        return redirect(url_for("editors_list"))
    email = request.form.get("email", "").strip()
    subjects_raw = request.form.get("subjects", "").strip()
    subjects_json = json.dumps([s.strip() for s in subjects_raw.split(",") if s.strip()], ensure_ascii=False)
    conn = get_conn()
    try:
        conn.execute("INSERT INTO editors (name, email, subjects) VALUES (?,?,?)",
                     (name, email, subjects_json))
        conn.commit()
        log_activity(conn, "editor", conn.execute("SELECT last_insert_rowid()").fetchone()[0], "添加编辑", f"姓名: {name}")
        flash(f"编辑 {name} 已添加", "success")
    except sqlite3.IntegrityError:
        flash("该编辑已存在", "danger")
    conn.close()
    return redirect(url_for("editors_list"))

@app.route("/editors/<int:eid>/toggle", methods=["POST"])
def editor_toggle(eid):
    conn = get_conn()
    r = conn.execute("SELECT active FROM editors WHERE id=?", (eid,)).fetchone()
    if r:
        new_val = 0 if r["active"] else 1
        conn.execute("UPDATE editors SET active=? WHERE id=?", (new_val, eid))
        conn.commit()
        log_activity(conn, "editor", eid, "切换状态", f"active={new_val}")
    conn.close()
    return redirect(url_for("editors_list"))

# ── 启动 ────────────────────────────────────────────

if __name__ == "__main__":
    port = 5000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    print(f"学报管理系统启动: http://127.0.0.1:{port}")
    print("按 Ctrl+C 停止")
    app.run(debug=True, host="127.0.0.1", port=port)
