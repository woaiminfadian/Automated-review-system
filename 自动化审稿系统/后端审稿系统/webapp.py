"""
学报数据库 Web 管理界面 — v2 多用户版
用法: python3 webapp.py [port]
"""
import sqlite3, os, json, sys, shutil
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "journal.db")
UPLOAD_DIR = os.path.join(DB_DIR, "uploads")

app = Flask(__name__, template_folder="../前端显示设计/templates")
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max upload

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "请先登录"

FIELDS = [
    "民法", "商法", "知识产权法", "经济法", "数据法",
    "民事诉讼法", "国际法", "刑法", "刑事诉讼法",
    "法理学", "宪法与行政法", "环境法", "劳动法",
    "法律史", "其他",
]
STATUSES = ["待处理", "派稿中", "审稿中", "返修中", "已录用", "已退稿", "作者撤稿"]
ROUNDS = ["一审", "二审", "再审", "终审", "外审"]
ASSIGN_STATUSES = ["待审", "审稿中", "已返回", "已通过", "返修", "退稿", "待确认"]
ALLOWED_EXT = {".docx", ".doc", ".pdf"}
DEFAULT_EDITOR_PASSWORD = os.environ.get("DEFAULT_EDITOR_PASSWORD", "123456")

# ── 自动化配置 ─────────────────────────────────────
from pathlib import Path
from journal_automation.config import load_config as _load_automation_config

_AUTOMATION_CONFIG_PATH = Path(DB_DIR) / "automation.config.json"
_automation_config = None


def get_automation_config():
    global _automation_config
    if _automation_config is None:
        if _AUTOMATION_CONFIG_PATH.exists():
            _automation_config = _load_automation_config(_AUTOMATION_CONFIG_PATH)
        else:
            raise RuntimeError("automation.config.json 未找到")
    return _automation_config

# ── Flask-Login User ──────────────────────────────────

class EditorUser(UserMixin):
    def __init__(self, row):
        d = dict(row)
        self.id = d["id"]
        self.name = d["name"]
        self.email = d.get("email", "")
        self.role = d.get("role", "编辑")
        self.subjects = d.get("subjects", "")

    @property
    def is_admin(self):
        return self.role in ("主编", "管理员")

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def load_user(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM editors WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return EditorUser(row) if row else None


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


def need_setup():
    """检查是否需要首次设置（无编辑有密码）"""
    conn = get_conn()
    cnt = conn.execute(
        "SELECT COUNT(*) FROM editors WHERE password_hash IS NOT NULL"
    ).fetchone()[0]
    conn.close()
    return cnt == 0


def ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


# Jinja2 自定义过滤器
@app.template_filter("json_loads")
def json_loads_filter(s):
    try:
        return json.loads(s) if s else []
    except:
        return []


@app.before_request
def before_request():
    if not need_setup():
        return
    # 首次设置，只允许访问 setup 和静态资源
    if request.endpoint not in ("setup", "static"):
        return redirect(url_for("setup"))


# ── 管理员装饰器 ───────────────────────────────────

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("无权限访问", "danger")
            return redirect(url_for("editor_dashboard"))
        return f(*args, **kwargs)
    return decorated


# ── 首次设置 ──────────────────────────────────────

@app.route("/setup", methods=["GET", "POST"])
def setup():
    if not need_setup():
        return redirect(url_for("login"))

    conn = get_conn()
    editors = conn.execute("SELECT id, name, email, role FROM editors ORDER BY name").fetchall()
    conn.close()

    if request.method == "POST":
        eid = request.form.get("editor_id", "").strip()
        password = request.form.get("password", "").strip()
        if not eid or not password:
            flash("请选择账号并设置密码", "danger")
            return render_template("setup.html", editors=editors)
        if len(password) < 4:
            flash("密码至少 4 位", "danger")
            return render_template("setup.html", editors=editors)
        h = generate_password_hash(password)
        conn = get_conn()
        conn.execute("UPDATE editors SET password_hash=?, role='主编' WHERE id=?", (h, eid))
        conn.commit()
        conn.close()
        flash("管理员账号已创建，请登录", "success")
        return redirect(url_for("login"))

    return render_template("setup.html", editors=editors)


# ── 认证 ──────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect_to_home()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "").strip()
        conn = get_conn()
        editor = conn.execute("SELECT * FROM editors WHERE name=?", (name,)).fetchone()
        conn.close()

        if editor and editor["password_hash"] and check_password_hash(editor["password_hash"], password):
            user = EditorUser(editor)
            login_user(user)
            # 更新最后登录时间
            conn = get_conn()
            conn.execute(
                "UPDATE editors SET last_login=? WHERE id=?",
                (datetime.now().strftime("%Y.%m.%d %H:%M"), editor["id"]),
            )
            conn.commit()
            conn.close()
            flash(f"欢迎回来, {editor['name']}!", "success")
            return redirect_to_home()
        flash("姓名或密码错误", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("已退出登录", "info")
    return redirect(url_for("login"))


def redirect_to_home():
    if current_user.is_admin:
        return redirect(url_for("dashboard"))
    return redirect(url_for("editor_dashboard"))


# ── 首页 / 仪表盘 (管理员) ──────────────────────────

@app.route("/")
@login_required
@admin_required
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
    
    # 各轮次审稿进度
    by_round = conn.execute("""
        SELECT a.round, a.status, COUNT(*) as cnt
        FROM assignments a
        GROUP BY a.round, a.status
        ORDER BY a.round, a.status
    """).fetchall()
    
    # 每位编辑的审稿量
    editor_stats = conn.execute("""
        SELECT e.name, e.subjects,
               COUNT(a.id) as total_assign,
               SUM(CASE WHEN a.status IN ('已返回','已通过','返修','退稿') THEN 1 ELSE 0 END) as done_assign
        FROM editors e
        LEFT JOIN assignments a ON a.editor_id = e.id
        WHERE e.active=1
        GROUP BY e.id
        ORDER BY done_assign DESC
    """).fetchall()
    
    recent_activity = conn.execute(
        "SELECT * FROM activity_log ORDER BY id DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return render_template("dashboard.html", total=total, by_status=by_status, by_field=by_field,
                           editor_count=editor_count, author_count=author_count,
                           pending_assign=pending_assign,
                           by_round=by_round, editor_stats=editor_stats,
                           recent_activity=recent_activity)
@app.route("/submissions")
@login_required
@admin_required
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
@login_required
@admin_required
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
@login_required
@admin_required
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
@login_required
@admin_required
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
@login_required
@admin_required
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
@login_required
@admin_required
def submission_delete(sid):
    conn = get_conn()
    conn.execute("DELETE FROM assignments WHERE submission_id=?", (sid,))
    conn.execute("DELETE FROM submissions WHERE id=?", (sid,))
    log_activity(conn, "submission", sid, "删除稿件", "")
    conn.commit()
    conn.close()
    flash("稿件已删除", "success")
    return redirect(url_for("submissions_list"))


# ── 派稿管理 (管理员) ─────────────────────────────

@app.route("/assignments")
@login_required
@admin_required
def assignments_list():
    conn = get_conn()
    round_f = request.args.get("round", "")
    status_f = request.args.get("status", "")
    editor_f = request.args.get("editor", "")

    sql = """
        SELECT a.id, a.round, a.status, a.result, a.assigned_date, a.result_date,
               a.score_total, a.review_opinion,
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
@login_required
@admin_required
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
@login_required
@admin_required
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
@login_required
@admin_required
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
@login_required
@admin_required
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


@app.route("/authors/<int:aid>/edit", methods=["POST"])
@login_required
@admin_required
def author_edit(aid):
    conn = get_conn()
    author = conn.execute("SELECT * FROM authors WHERE id=?", (aid,)).fetchone()
    if not author:
        conn.close()
        flash("作者不存在", "danger")
        return redirect(url_for("authors_list"))
    name = request.form.get("name", "").strip()
    if not name:
        flash("请填写姓名", "danger")
        conn.close()
        return redirect(url_for("authors_list"))
    conn.execute(
        "UPDATE authors SET name=?, email=?, phone=?, affiliation=?, department=?, grade=?, address=? WHERE id=?",
        (name, request.form.get("email", "").strip(), request.form.get("phone", "").strip(),
         request.form.get("affiliation", "").strip(), request.form.get("department", "").strip(),
         request.form.get("grade", "").strip(), request.form.get("address", "").strip(), aid),
    )
    conn.commit()
    log_activity(conn, "author", aid, "编辑作者", f"姓名: {name}")
    conn.close()
    flash(f"作者 {name} 已更新", "success")
    return redirect(url_for("authors_list"))


@app.route("/authors/<int:aid>/delete", methods=["POST"])
@login_required
@admin_required
def author_delete(aid):
    conn = get_conn()
    conn.execute("UPDATE submissions SET author1_id=NULL WHERE author1_id=?", (aid,))
    conn.execute("UPDATE submissions SET author2_id=NULL WHERE author2_id=?", (aid,))
    conn.execute("DELETE FROM authors WHERE id=?", (aid,))
    log_activity(conn, "author", aid, "删除作者", "")
    conn.commit()
    conn.close()
    flash("作者已删除", "success")
    return redirect(url_for("authors_list"))


# ── 编辑管理 (管理员) ─────────────────────────────

@app.route("/editors")
@login_required
@admin_required
def editors_list():
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, name, email, role, subjects, active, password_hash, password_default, last_login FROM editors ORDER BY active DESC, subjects, name"
    ).fetchall()]
    for r in rows:
        if r["subjects"]:
            try:
                r["subjects_list"] = json.loads(r["subjects"])
            except:
                r["subjects_list"] = [r["subjects"]]
        else:
            r["subjects_list"] = []
        r["has_password"] = bool(r["password_hash"])
    conn.close()
    return render_template("editors.html", editors=rows)


@app.route("/editors/add", methods=["POST"])
@login_required
@admin_required
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
        cur = conn.execute("INSERT INTO editors (name, email, subjects) VALUES (?,?,?)",
                          (name, email, subjects_json))
        eid = cur.lastrowid
        h = generate_password_hash(DEFAULT_EDITOR_PASSWORD)
        conn.execute("UPDATE editors SET password_hash=?, password_default=1 WHERE id=?", (h, eid))
        conn.commit()
        log_activity(conn, "editor", eid, "添加编辑", f"姓名: {name}")
        flash(f"编辑 {name} 已添加，默认密码: {DEFAULT_EDITOR_PASSWORD}", "success")
    except sqlite3.IntegrityError:
        flash("该编辑已存在", "danger")
    conn.close()
    return redirect(url_for("editors_list"))


@app.route("/editors/<int:eid>/toggle", methods=["POST"])
@login_required
@admin_required
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


@app.route("/editors/<int:eid>/edit", methods=["POST"])
@login_required
@admin_required
def editor_edit(eid):
    conn = get_conn()
    editor = conn.execute("SELECT * FROM editors WHERE id=?", (eid,)).fetchone()
    if not editor:
        conn.close()
        flash("编辑不存在", "danger")
        return redirect(url_for("editors_list"))
    name = request.form.get("name", "").strip()
    if not name:
        flash("请填写姓名", "danger")
        conn.close()
        return redirect(url_for("editors_list"))
    email = request.form.get("email", "").strip()
    subjects_raw = request.form.get("subjects", "").strip()
    subjects_json = json.dumps([s.strip() for s in subjects_raw.split(",") if s.strip()], ensure_ascii=False)
    conn.execute("UPDATE editors SET name=?, email=?, subjects=? WHERE id=?",
                  (name, email, subjects_json, eid))
    conn.commit()
    log_activity(conn, "editor", eid, "编辑编辑", f"姓名: {name}")
    conn.close()
    flash(f"编辑 {name} 已更新", "success")
    return redirect(url_for("editors_list"))


@app.route("/editors/<int:eid>/delete", methods=["POST"])
@login_required
@admin_required
def editor_delete(eid):
    conn = get_conn()
    editor = conn.execute("SELECT name FROM editors WHERE id=?", (eid,)).fetchone()
    if not editor:
        conn.close()
        flash("编辑不存在", "danger")
        return redirect(url_for("editors_list"))
    conn.execute("DELETE FROM assignments WHERE editor_id=?", (eid,))
    conn.execute("DELETE FROM editors WHERE id=?", (eid,))
    log_activity(conn, "editor", eid, "删除编辑", f"姓名: {editor['name']}")
    conn.commit()
    conn.close()
    flash(f"编辑 {editor['name']} 已删除", "success")
    return redirect(url_for("editors_list"))


@app.route("/editors/<int:eid>/set-password", methods=["POST"])
@login_required
@admin_required
def editor_set_password(eid):
    conn = get_conn()
    editor = conn.execute("SELECT * FROM editors WHERE id=?", (eid,)).fetchone()
    if not editor:
        conn.close()
        flash("编辑不存在", "danger")
        return redirect(url_for("editors_list"))
    password = request.form.get("password", "").strip()
    if not password or len(password) < 4:
        flash("密码至少 4 位", "danger")
        conn.close()
        return redirect(url_for("editors_list"))
    h = generate_password_hash(password)
    conn.execute("UPDATE editors SET password_hash=?, password_default=0 WHERE id=?", (h, eid))
    conn.commit()
    log_activity(conn, "editor", eid, "设置密码", f"编辑: {editor['name']}")
    conn.close()
    flash(f"编辑 {editor['name']} 密码已设置", "success")
    return redirect(url_for("editors_list"))


# ═══════════════════════════════════════════════════════
# 编辑端
# ═══════════════════════════════════════════════════════

@app.route("/editor/")
@login_required
def editor_dashboard():
    conn = get_conn()
    eid = current_user.id

    # 检查是否仍在使用默认密码
    editor = conn.execute("SELECT password_default FROM editors WHERE id=?", (eid,)).fetchone()
    password_default = editor["password_default"] if editor and editor["password_default"] else 0

    # 我的审稿列表
    assigns = conn.execute("""
        SELECT a.id, a.round, a.status, a.result, a.assigned_date, a.deadline,
               a.score_total, a.review_opinion, a.reviewed_at,
               a.file_review, a.file_annotated,
               s.id AS sid, s.title, s.field, s.submission_type,
               au.name AS author_name, au.affiliation AS author_aff
        FROM assignments a
        JOIN submissions s ON a.submission_id = s.id
        LEFT JOIN authors au ON s.author1_id = au.id
        WHERE a.editor_id=?
        ORDER BY a.status='待审' DESC, a.assigned_date DESC
    """, (eid,)).fetchall()

    stats = {
        "total": len(assigns),
        "pending": sum(1 for a in assigns if a["status"] == "待审"),
        "reviewing": sum(1 for a in assigns if a["status"] == "审稿中"),
        "done": sum(1 for a in assigns if a["status"] in ("已返回", "已通过", "返修", "退稿")),
    }
    conn.close()
    return render_template("editor_dashboard.html", assigns=assigns, stats=stats,
                           password_default=password_default)


@app.route("/editor/change-password", methods=["GET", "POST"])
@login_required
def editor_change_password():
    if request.method == "POST":
        old_pw = request.form.get("old_password", "").strip()
        new_pw = request.form.get("new_password", "").strip()
        confirm = request.form.get("confirm_password", "").strip()

        conn = get_conn()
        editor = conn.execute("SELECT * FROM editors WHERE id=?", (current_user.id,)).fetchone()

        if not editor["password_hash"] or not check_password_hash(editor["password_hash"], old_pw):
            conn.close()
            flash("当前密码错误", "danger")
            return render_template("editor_change_password.html")

        if len(new_pw) < 4:
            conn.close()
            flash("新密码至少 4 位", "danger")
            return render_template("editor_change_password.html")

        if new_pw != confirm:
            conn.close()
            flash("两次密码输入不一致", "danger")
            return render_template("editor_change_password.html")

        h = generate_password_hash(new_pw)
        conn.execute("UPDATE editors SET password_hash=?, password_default=0 WHERE id=?", (h, current_user.id))
        conn.commit()
        conn.close()
        flash("密码已修改成功", "success")
        return redirect(url_for("editor_dashboard"))

    return render_template("editor_change_password.html")


@app.route("/editor/review/<int:aid>", methods=["GET", "POST"])
@login_required
def editor_review(aid):
    conn = get_conn()
    assign = conn.execute("""
        SELECT a.*, s.title, s.field, s.submission_type,
               au.name AS author_name, au.affiliation AS author_aff
        FROM assignments a
        JOIN submissions s ON a.submission_id = s.id
        LEFT JOIN authors au ON s.author1_id = au.id
        WHERE a.id=?
    """, (aid,)).fetchone()

    if not assign:
        conn.close()
        flash("派稿记录不存在", "danger")
        return redirect(url_for("editor_dashboard"))

    # 只能看自己的
    if assign["editor_id"] != current_user.id and not current_user.is_admin:
        conn.close()
        flash("这不是分配给您的审稿任务", "danger")
        return redirect(url_for("editor_dashboard"))

    if request.method == "POST":
        score_topic = _float_or_none(request.form.get("score_topic"))
        score_argument = _float_or_none(request.form.get("score_argument"))
        score_innovation = _float_or_none(request.form.get("score_innovation"))
        score_standard = _float_or_none(request.form.get("score_standard"))
        score_total = _float_or_none(request.form.get("score_total"))
        review_opinion = request.form.get("review_opinion", "").strip()
        review_comment = request.form.get("review_comment", "").strip()

        # 文件上传
        file_review = assign.get("file_review", "")
        file_annotated = assign.get("file_annotated", "")
        ensure_upload_dir()

        if "file_review" in request.files:
            f = request.files["file_review"]
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext in ALLOWED_EXT:
                    subdir = os.path.join(UPLOAD_DIR, f"review_{aid}")
                    os.makedirs(subdir, exist_ok=True)
                    fname = f"审稿评分表{ext}"
                    f.save(os.path.join(subdir, fname))
                    file_review = f"uploads/review_{aid}/{fname}"

        if "file_annotated" in request.files:
            f = request.files["file_annotated"]
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext in ALLOWED_EXT:
                    subdir = os.path.join(UPLOAD_DIR, f"review_{aid}")
                    os.makedirs(subdir, exist_ok=True)
                    fname = f"【批注版】{assign['title'][:20]}{ext}"
                    f.save(os.path.join(subdir, fname))
                    file_annotated = f"uploads/review_{aid}/{fname}"

        now = datetime.now().strftime("%Y.%m.%d %H:%M")
        conn.execute("""
            UPDATE assignments SET
                score_topic=?, score_argument=?, score_innovation=?, score_standard=?, score_total=?,
                review_opinion=?, review_comment=?, file_review=?, file_annotated=?,
                status='已返回', reviewed_at=?
            WHERE id=?
        """, (score_topic, score_argument, score_innovation, score_standard, score_total,
              review_opinion, review_comment, file_review, file_annotated, now, aid))

        # 更新稿件状态
        sid = assign["submission_id"]
        conn.execute("UPDATE submissions SET status='审稿中', updated_at=datetime('now','localtime') WHERE id=? AND status='派稿中'", (sid,))
        log_activity(conn, "assignment", aid, "编辑提交审稿", f"总分: {score_total}, 意见: {review_opinion}")
        conn.commit()
        conn.close()
        flash("审稿意见已提交!", "success")
        return redirect(url_for("editor_dashboard"))

    conn.close()
    return render_template("editor_review.html", assign=assign)


def _float_or_none(v):
    try:
        return float(v) if v else None
    except (ValueError, TypeError):
        return None


# ── 下载上传的文件 ────────────────────────────────

@app.route("/uploads/<path:filename>")
@login_required
def download_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


from flask import send_from_directory


# ═══════════════════════════════════════════════════════
# 邮件收稿 API
# ═══════════════════════════════════════════════════════


@app.route("/email/status")
@login_required
@admin_required
def email_status():
    conn = get_conn()
    new_count = conn.execute("SELECT COUNT(*) FROM email_staging WHERE status='待录入'").fetchone()[0]
    conn.close()
    return {"new_count": new_count, "total_pending": new_count}


@app.route("/api/email/fetch", methods=["POST"])
@login_required
@admin_required
def api_email_fetch():
    try:
        config = get_automation_config()
    except RuntimeError as e:
        return {"error": str(e)}, 500

    conn = get_conn()
    row = conn.execute("SELECT value FROM email_sync_state WHERE key='last_uid'").fetchone()
    last_uid = row["value"] if row else None

    from journal_automation.mail import fetch_messages_from_imap, parse_message, is_submission_email
    from journal_automation.metadata import parse_submission
    from journal_automation.utils import sanitize_filename

    try:
        messages = list(fetch_messages_from_imap(config, after_uid=last_uid, limit=20))
    except Exception as e:
        conn.close()
        return {"error": f"IMAP连接失败: {str(e)}"}, 500

    summary = {"new": 0, "skipped_non_submission": 0, "already_staged": 0}
    staged = []
    max_uid = last_uid
    ensure_upload_dir()

    for uid, raw in messages:
        if uid and (max_uid is None or int(uid) > int(max_uid)):
            max_uid = uid

        message = parse_message(raw)
        message_id = (message.get("Message-ID") or f"<local-{uid}>").strip()

        if not is_submission_email(message):
            summary["skipped_non_submission"] += 1
            continue

        existing = conn.execute(
            "SELECT id FROM email_staging WHERE message_id=?", (message_id,)
        ).fetchone()
        if existing:
            summary["already_staged"] += 1
            continue

        try:
            record, attachments = parse_submission(message_id, uid, message, config)
        except Exception:
            summary["skipped_non_submission"] += 1
            continue

        cur = conn.execute(
            """INSERT INTO email_staging
               (uid, message_id, subject_line, sender, sender_name, sent_at,
                title, field, authors_json, author_info, contact_info, body_text,
                needs_review, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                uid, message_id,
                record.subject_line, record.sender, record.sender_name, record.sent_at,
                record.title, record.discipline,
                json.dumps(record.authors, ensure_ascii=False),
                record.author_info, record.contact_info, record.body_text,
                1 if record.needs_manual_review else 0,
                "待录入",
            ),
        )
        staging_id = cur.lastrowid

        attachments_info = []
        if attachments:
            staging_dir = os.path.join(UPLOAD_DIR, "email_staging", str(staging_id))
            os.makedirs(staging_dir, exist_ok=True)
            for att in attachments:
                safe_name = sanitize_filename(att.filename) if att.filename else "未命名附件"
                fpath = os.path.join(staging_dir, safe_name)
                with open(fpath, "wb") as f:
                    f.write(att.payload)
                attachments_info.append({
                    "filename": att.filename or "未命名附件",
                    "content_type": att.content_type,
                    "staged_path": f"uploads/email_staging/{staging_id}/{safe_name}",
                    "category": att.category,
                })

        conn.execute(
            "UPDATE email_staging SET attachments_json=? WHERE id=?",
            (json.dumps(attachments_info, ensure_ascii=False), staging_id),
        )
        conn.commit()

        summary["new"] += 1

        staged.append({
            "id": staging_id, "uid": uid, "message_id": message_id,
            "subject_line": record.subject_line, "sender": record.sender,
            "sender_name": record.sender_name, "sent_at": record.sent_at,
            "title": record.title, "field": record.discipline,
            "authors": record.authors, "author_info": record.author_info,
            "contact_info": record.contact_info,
            "attachments": attachments_info,
            "needs_review": record.needs_manual_review,
            "status": "待录入",
        })

    if max_uid and max_uid != last_uid:
        conn.execute(
            "INSERT OR REPLACE INTO email_sync_state (key, value) VALUES ('last_uid', ?)",
            (str(max_uid),),
        )
        conn.commit()

    conn.close()
    return {"summary": summary, "staged": staged}


@app.route("/api/email/import/<int:staging_id>", methods=["POST"])
@login_required
@admin_required
def api_email_import(staging_id):
    conn = get_conn()
    staging = conn.execute("SELECT * FROM email_staging WHERE id=?", (staging_id,)).fetchone()
    if not staging:
        conn.close()
        return {"success": False, "error": "暂存记录不存在"}, 404

    if staging["status"] == "已录入":
        conn.close()
        return {"success": False, "error": "该邮件已录入"}, 400

    data = request.get_json() or {}
    title = (data.get("title") or staging["title"] or "").strip()
    field = (data.get("field") or staging["field"] or "").strip()
    authors_data = data.get("authors", [])
    received_date = (data.get("received_date") or staging["sent_at"] or "").strip()
    submission_type = (data.get("submission_type") or "正常来稿").strip()

    if not title or not field:
        conn.close()
        return {"success": False, "error": "标题和学科不能为空"}, 400

    author_ids = []
    for author in authors_data:
        name = (author.get("name") or "").strip()
        if not name:
            continue
        email_addr = (author.get("email") or "").strip()
        phone = (author.get("phone") or "").strip()
        affiliation = (author.get("affiliation") or "").strip()
        grade = (author.get("grade") or "").strip()

        existing = conn.execute(
            "SELECT id FROM authors WHERE name=? AND (email=? OR email='' OR ?='')",
            (name, email_addr, email_addr),
        ).fetchone()
        if existing:
            author_ids.append(existing["id"])
        else:
            cur = conn.execute(
                "INSERT INTO authors (name, email, phone, affiliation, grade) VALUES (?,?,?,?,?)",
                (name, email_addr, phone, affiliation, grade),
            )
            author_ids.append(cur.lastrowid)

    if not author_ids:
        try:
            parsed_authors = json.loads(staging["authors_json"] or "[]")
            for name in parsed_authors:
                name = name.strip()
                if not name:
                    continue
                existing = conn.execute("SELECT id FROM authors WHERE name=?", (name,)).fetchone()
                if existing:
                    author_ids.append(existing["id"])
                else:
                    cur = conn.execute("INSERT INTO authors (name) VALUES (?)", (name,))
                    author_ids.append(cur.lastrowid)
        except Exception:
            pass

    aid1 = author_ids[0] if len(author_ids) > 0 else None
    aid2 = author_ids[1] if len(author_ids) > 1 else None

    try:
        attachments_info = json.loads(staging["attachments_json"] or "[]")
    except Exception:
        attachments_info = []

    main_file_path = attachments_info[0].get("staged_path", "") if attachments_info else ""

    cur = conn.execute(
        """INSERT INTO submissions
           (title, field, submission_type, author1_id, author2_id, received_date, status, file_path, notes)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (title, field, submission_type, aid1, aid2, received_date, "待处理",
         main_file_path, f"邮件导入 (message_id: {staging['message_id']})"),
    )
    sid = cur.lastrowid

    if attachments_info:
        final_dir = os.path.join(UPLOAD_DIR, f"submission_{sid}")
        os.makedirs(final_dir, exist_ok=True)
        final_paths = []
        for att in attachments_info:
            src = os.path.join(DB_DIR, att["staged_path"])
            if os.path.exists(src):
                dst = os.path.join(final_dir, os.path.basename(att["staged_path"]))
                shutil.move(src, dst)
                final_paths.append(f"uploads/submission_{sid}/{os.path.basename(att['staged_path'])}")
        if final_paths:
            conn.execute("UPDATE submissions SET file_path=? WHERE id=?", (final_paths[0], sid))

    conn.execute("UPDATE email_staging SET status='已录入' WHERE id=?", (staging_id,))
    log_activity(conn, "submission", sid, "邮件导入",
                 f"标题: {title}, 发件人: {staging['sender_name'] or ''}")
    conn.commit()
    conn.close()

    return {"success": True, "submission_id": sid, "message": "稿件已录入"}


@app.route("/email/inbox")
@login_required
@admin_required
def email_inbox():
    conn = get_conn()
    status_f = request.args.get("status", "")
    if status_f:
        rows = conn.execute(
            "SELECT * FROM email_staging WHERE status=? ORDER BY id DESC LIMIT 50",
            (status_f,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM email_staging ORDER BY id DESC LIMIT 50"
        ).fetchall()

    staging_list = []
    for r in rows:
        d = dict(r)
        try:
            d["authors"] = json.loads(d["authors_json"] or "[]")
        except Exception:
            d["authors"] = []
        try:
            d["attachments"] = json.loads(d["attachments_json"] or "[]")
        except Exception:
            d["attachments"] = []
        staging_list.append(d)

    pending_count = conn.execute(
        "SELECT COUNT(*) FROM email_staging WHERE status='待录入'"
    ).fetchone()[0]
    imported_today = conn.execute(
        "SELECT COUNT(*) FROM email_staging WHERE status='已录入' AND date(created_at)=date('now','localtime')"
    ).fetchone()[0]
    conn.close()

    return render_template("email_inbox.html", staging_list=staging_list,
                           pending_count=pending_count, imported_today=imported_today,
                           status_f=status_f, fields=FIELDS)


@app.route("/email/staging/<int:staging_id>/update", methods=["POST"])
@login_required
@admin_required
def email_staging_update(staging_id):
    conn = get_conn()
    staging = conn.execute("SELECT * FROM email_staging WHERE id=?", (staging_id,)).fetchone()
    if not staging:
        conn.close()
        return {"success": False, "error": "暂存记录不存在"}, 404

    data = request.get_json() or {}
    title = data.get("title", staging["title"])
    field = data.get("field", staging["field"])
    authors_json = data.get("authors_json")
    contact_info = data.get("contact_info", staging["contact_info"])

    if authors_json is not None:
        if isinstance(authors_json, list):
            authors_json = json.dumps(authors_json, ensure_ascii=False)
        conn.execute(
            "UPDATE email_staging SET title=?, field=?, authors_json=?, contact_info=? WHERE id=?",
            (title, field, authors_json, contact_info, staging_id),
        )
    else:
        conn.execute(
            "UPDATE email_staging SET title=?, field=?, contact_info=? WHERE id=?",
            (title, field, contact_info, staging_id),
        )

    conn.commit()
    conn.close()
    return {"success": True}


@app.route("/email/staging/<int:staging_id>/dismiss", methods=["POST"])
@login_required
@admin_required
def email_staging_dismiss(staging_id):
    conn = get_conn()
    conn.execute("UPDATE email_staging SET status='已忽略' WHERE id=?", (staging_id,))
    conn.commit()
    conn.close()
    return {"success": True}

# ── 启动 ────────────────────────────────────────────

if __name__ == "__main__":
    ensure_upload_dir()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    debug = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")
    if host != "127.0.0.1" and debug:
        print("WARNING: DEBUG mode enabled on non-localhost. This is a security risk.")
    print(f"学报管理系统 v2 启动: http://{host}:{port}")
    print("按 Ctrl+C 停止")
    app.run(debug=debug, host=host, port=port)
