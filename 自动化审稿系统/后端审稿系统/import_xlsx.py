"""
从 私法组审稿（2025—2026学年）.xlsx 导入数据到 journal.db
"""
import sqlite3
import openpyxl
import re
import os
import sys

DB = os.path.join(os.path.dirname(__file__), "journal.db")
XLSX = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "私法组审稿（2025—2026学年）.xlsx")

def get_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def find_or_create_author(conn, name, affiliation_str="", phone="", address=""):
    """按姓名查找作者，不存在则创建"""
    if not name or name.strip() == "":
        return None
    name = name.strip()
    row = conn.execute("SELECT id, affiliation, grade FROM authors WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    # 解析 affiliation 字段
    affiliation, grade, department = parse_affiliation(affiliation_str)
    cur = conn.execute(
        "INSERT INTO authors (name, email, phone, address, affiliation, department, grade) VALUES (?,?,?,?,?,?,?)",
        (name, "", phone, address, affiliation, department, grade)
    )
    conn.commit()
    return cur.lastrowid

def parse_affiliation(s):
    """从 '中国政法大学硕士研究生' 解析出学校、院系、年级"""
    if not s:
        return ("", "", "")
    s = s.strip()
    # 常见模式: 学校+院系+年级+研究生/硕士/博士
    grade = ""
    for g in ["博士研究生", "博士", "硕士研究生", "硕士", "研究生在读", "研究生", "本科生", "教师", "博士后"]:
        if g in s:
            grade = g
            break

    # 提取学校名
    affiliation = s
    for uni in ["中国政法大学", "北京大学", "清华大学", "中国人民大学", "外交学院", "华东理工大学",
                 "中央财经大学", "对外经济贸易大学", "北京理工大学", "北京师范大学", "上海交通大学",
                 "复旦大学", "南京大学", "武汉大学", "厦门大学", "吉林大学", "中南财经政法大学",
                 "西南政法大学", "华东政法大学", "西北政法大学", "华中科技大学", "中山大学",
                 "浙江大学", "山东大学", "四川大学", "南开大学", "天津大学", "同济大学",
                 "湖南大学", "重庆大学", "西安交通大学", "兰州大学", "暨南大学", "华南理工大学",
                 "中国海洋大学", "中央民族大学", "郑州大学", "云南大学", "新疆大学",
                 "中国社会科学院大学", "中国青年政治学院", "北京邮电大学", "北京外国语大学",
                 "上海政法学院", "中国计量大学", "大连海事大学", "海南大学", "北京工商大学",
                 "上海大学", "上海对外经贸大学", "华东师范大学", "安徽大学", "北京航空航天大学",
                 "北京科技大学", "北京联合大学", "北京林业大学", "北京体育大学", "北京外国语大学",
                 "北京物资学院", "北京语言大学", "常州大学", "东北大学", "东北林业大学",
                 "东北师范大学", "东华大学", "东南大学", "福州大学", "广东财经大学", "广东外语外贸大学",
                 "广西大学", "广州大学", "贵州大学", "哈尔滨工程大学", "哈尔滨工业大学",
                 "杭州师范大学", "河北大学", "河北经贸大学", "河海大学", "河南大学", "黑龙江大学",
                 "湖北大学", "湖南工商大学", "湖南师范大学", "华北电力大学", "华东交通大学",
                 "华南师范大学", "华侨大学", "华中农业大学", "华中师范大学", "江西财经大学",
                 "江西理工大学", "昆明理工大学", "辽宁大学", "南昌大学", "南方医科大学",
                 "南京财经大学", "南京工业大学", "南京航空航天大学", "南京理工大学", "南京师范大学",
                 "南京信息工程大学", "南京审计大学", "南宁师范大学", "南通大学", "宁波大学",
                 "青岛大学", "山东财经大学", "山东科技大学", "山西大学", "陕西师范大学",
                 "汕头大学", "上海财经大学", "上海海事大学", "上海师范大学", "深圳大学",
                 "沈阳工业大学", "沈阳师范大学", "石河子大学", "首都经济贸易大学", "首都师范大学",
                 "四川外国语大学", "苏州大学", "太原理工大学", "天津财经大学", "天津工业大学",
                 "天津商业大学", "天津师范大学", "外交学院", "温州大学", "武汉理工大学",
                 "西安财经大学", "西安建筑科技大学", "西北大学", "西北工业大学", "西南财经大学",
                 "西南大学", "西南交通大学", "西南民族大学", "湘潭大学", "新疆财经大学",
                 "燕山大学", "扬州大学", "长安大学", "长江大学", "长沙理工大学", "浙江财经大学",
                 "浙江工商大学", "浙江工业大学", "浙江理工大学", "浙江师范大学", "郑州大学",
                 "中国传媒大学", "中国人民公安大学", "中国石油大学", "中国刑事警察学院",
                 "中国音乐学院", "中南大学", "中南民族大学", "中央司法警官学院", "中央戏剧学院",
                 "中央音乐学院", "重庆工商大学", "重庆邮电大学"]:
        if uni in s:
            affiliation = uni
            break

    # 尝试提取院系
    department = ""
    dept_match = re.search(r'([^0-9]+?)(?:法学院|学院|系|研究院|研究所|中心)', s)
    if dept_match:
        dept_full = dept_match.group(0)
        if dept_full not in affiliation:  # 避免重复
            department = dept_full

    return (affiliation, grade, department)

def parse_date(d):
    """解析日期 YYYY.MM.DD 或 YYYY.M.D 等格式"""
    if not d:
        return ""
    d = str(d).strip()
    # 修复明显的 typo: 225.12.01 -> 2025.12.01
    d = re.sub(r'\b225\.', '2025.', d)
    m = re.match(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', d)
    if m:
        return f"{m.group(1)}.{int(m.group(2)):02d}.{int(m.group(3)):02d}"
    return d

def parse_review_entry(entry):
    """解析单条审稿记录，返回 (date, editors, action)"""
    entry = entry.strip()
    if not entry:
        return None

    # 跳过纯编辑姓名或括号
    if entry in ["已转出", "作者撤稿", "未确认"] or entry.startswith("综合"):
        return None

    # "字数不足退稿（杨铮）"
    m = re.match(r'(\d{4}\.\d{1,2}\.\d{1,2})\s*(.+?)[（(]([^）)]+)[）)]', entry)
    if m:
        date = parse_date(m.group(1))
        action_text = m.group(2).strip()
        editors_str = m.group(3).strip()
        editors = [e.strip() for e in re.split(r'[,、/]', editors_str) if e.strip()]
        # 提取 action (返修/通过/退稿/录用/小修/待商榷/预录用)
        action = ""
        for a in ["返修后录用", "返修后通过", "预录用", "录用", "退稿", "通过", "返修", "小修", "待商榷", "作者撤稿"]:
            if a in action_text:
                action = a
                break
        return {"date": date, "editors": editors, "action": action, "raw": entry}

    # 无日期的: "退稿（韩佩芝）", "李文静（派稿但未回复）"
    m2 = re.match(r'([^（(]+)[（(]([^）)]+)[）)]', entry)
    if m2:
        action = m2.group(1).strip()
        editors_str = m2.group(2).strip()
        # 过滤 "派稿但未回复" 这种情况
        if editors_str in ["派稿但未回复"]:
            return None
        editors = [e.strip() for e in re.split(r'[,、/]', editors_str) if e.strip()]
        return {"date": "", "editors": editors, "action": action, "raw": entry}

    return None

def determine_status(review_entries_all, issue_val):
    """根据所有审稿记录和录用时间确定稿件状态"""
    # 如果组内录用时间有值 → 已录用
    if issue_val and str(issue_val).strip():
        return "已录用"

    # 收集所有有日期的记录，按时间排序
    dated = [r for r in review_entries_all if r and r.get("date")]
    dated.sort(key=lambda x: x["date"])

    # 检查是否有 "已转出" 或 "作者撤稿"
    has_transferred = False
    has_withdrawn = False
    for col_val in review_entries_all:
        if not col_val:
            continue
        if isinstance(col_val, str):
            if "已转出" in col_val:
                has_transferred = True
            if "作者撤稿" in col_val:
                has_withdrawn = True

    if has_withdrawn:
        return "作者撤稿"

    # 看审稿记录的整体情况
    if not dated:
        if has_transferred:
            return "已退稿"
        return "待处理"

    # 看最新一条记录的操作
    last = dated[-1]
    last_action = last.get("action", "")

    if last_action in ["录用", "返修后录用", "预录用"]:
        return "已录用"
    elif last_action in ["退稿"]:
        return "已退稿"
    elif last_action in ["返修", "小修", "返修后通过"]:
        return "返修中"
    elif last_action in ["通过", "待商榷"]:
        return "审稿中"
    else:
        # 没有明确操作但有审稿记录
        return "审稿中"

def parse_review_column(col_val):
    """解析一列审稿记录（可能含多行）"""
    if not col_val or str(col_val).strip() in ("", "None"):
        return []
    text = str(col_val).strip()
    entries = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line in ("/",):
            continue
        parsed = parse_review_entry(line)
        if parsed:
            entries.append(parsed)
        else:
            # 记录未解析的原始文本
            entries.append({"date": "", "editors": [], "action": "", "raw": line})
    return entries

def main():
    print(f"读取 XLSX: {XLSX}")
    wb = openpyxl.load_workbook(XLSX)
    ws = wb['Sheet1']

    conn = get_conn()

    # 统计
    total = 0
    created_submissions = 0
    created_assignments = 0
    created_authors = 0
    skipped = 0
    errors = []

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        seq = row[0]  # 序号
        date_str = str(row[1] or "").strip()
        title = str(row[2] or "").strip()
        field = str(row[3] or "").strip()
        sub_type = str(row[4] or "正常来稿").strip()
        author1_name = str(row[5] or "").strip()
        author1_affil = str(row[6] or "").strip()
        author2_name = str(row[7] or "").strip()
        author2_affil = str(row[8] or "").strip()
        col_j = str(row[9] or "").strip()
        col_k = str(row[10] or "").strip()
        col_l = str(row[11] or "").strip()
        col_m = str(row[12] or "").strip()
        issue_val = str(row[13] or "").strip()
        contact = str(row[14] or "").strip()
        notes = str(row[15] or "").strip()

        if not title and not author1_name and seq is None:
            continue

        total += 1

        # 解析联系电话和地址
        phone = ""
        address = ""
        email = ""
        if contact:
            # 提取电话
            phone_m = re.search(r'电话[：:]?\s*(\d{11}|\d{3,4}-\d{7,8})', contact)
            if phone_m:
                phone = phone_m.group(1)
            # 提取邮箱
            email_m = re.search(r'电子[邮信]箱[：:]?\s*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', contact)
            if email_m:
                email = email_m.group(1)
            # 提取通讯地址
            addr_m = re.search(r'(?:通讯)?地址[：:]?\s*(.+)', contact)
            if addr_m:
                address = addr_m.group(1).strip()

        # 规范化来稿方向
        if field in ("空", "", "None"):
            field = "其他"
        # 处理复杂方向：取第一个方向
        if "/" in field or "、" in field:
            first_field = re.split(r'[/、]', field)[0].strip()
            if first_field:
                field = first_field

        try:
            # 1. 创建或查找作者
            a1_id = find_or_create_author(conn, author1_name, author1_affil, phone, address)
            a2_id = find_or_create_author(conn, author2_name, author2_affil)
            if a1_id is None and a2_id is None:
                errors.append(f"Row {row_idx}: 无作者信息，跳过")
                skipped += 1
                continue

            # 2. 解析审稿记录，确定状态
            all_entries = []
            for col_val in [col_j, col_k, col_l, col_m]:
                all_entries.extend(parse_review_column(col_val))

            status = determine_status(all_entries, issue_val)

            # 整理 notes
            notes_parts = []
            if notes and notes != "None":
                notes_parts.append(notes)
            # 将未解析的审稿信息附加到备注
            for entry in all_entries:
                if entry and entry.get("raw") and not entry.get("action"):
                    notes_parts.append(f"[审稿] {entry['raw']}")
            combined_notes = "; ".join(notes_parts) if notes_parts else ""

            # 3. 创建稿件
            received_date = parse_date(date_str)
            cur = conn.execute(
                """INSERT INTO submissions
                   (title, field, submission_type, author1_id, author2_id, received_date, status, issue, notes)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (title, field, sub_type, a1_id, a2_id, received_date, status, issue_val, combined_notes)
            )
            sid = cur.lastrowid
            created_submissions += 1

            # 4. 创建派稿记录(assignment)
            round_names = ["一审", "二审", "再审", "终审"]
            for round_name, col_val in zip(round_names, [col_j, col_k, col_l, col_m]):
                if not col_val or col_val.strip() in ("", "None", "/", "已转出"):
                    continue
                entries = parse_review_column(col_val)
                for entry in entries:
                    if not entry or not entry.get("editors"):
                        continue
                    for editor_name in entry["editors"]:
                        editor_row = conn.execute(
                            "SELECT id FROM editors WHERE name = ?", (editor_name,)
                        ).fetchone()
                        if not editor_row:
                            # 编辑不在数据库中，尝试添加
                            try:
                                conn.execute(
                                    "INSERT INTO editors (name, subjects) VALUES (?, ?)",
                                    (editor_name, "[]")
                                )
                                conn.commit()
                                editor_id = conn.execute(
                                    "SELECT id FROM editors WHERE name = ?", (editor_name,)
                                ).fetchone()["id"]
                                created_authors += 1
                            except:
                                continue
                        else:
                            editor_id = editor_row["id"]

                        # 确定 assignment 状态和结果
                        assign_status = "待审"
                        assign_result = None
                        action = entry.get("action", "")
                        assign_date = entry.get("date", "")
                        if action == "通过":
                            assign_status = "已通过"
                            assign_result = "通过"
                        elif action in ("返修", "小修"):
                            assign_status = "返修"
                            assign_result = "返修"
                        elif action in ("退稿",):
                            assign_status = "退稿"
                            assign_result = "退稿"
                        elif action in ("录用", "返修后录用", "预录用", "返修后通过"):
                            assign_status = "已通过"
                            assign_result = "通过"
                        elif action == "待商榷":
                            assign_status = "审稿中"
                            assign_result = None

                        try:
                            conn.execute(
                                """INSERT INTO assignments
                                   (submission_id, editor_id, round, assigned_date, status, result, result_date)
                                   VALUES (?,?,?,?,?,?,?)""",
                                (sid, editor_id, round_name, assign_date, assign_status, assign_result, assign_date)
                            )
                            created_assignments += 1
                        except sqlite3.IntegrityError:
                            pass

            conn.commit()

            if total % 20 == 0:
                print(f"  已处理 {total} 行...")

        except Exception as e:
            conn.rollback()
            errors.append(f"Row {row_idx} [{title[:20]}]: {e}")

    conn.close()
    print(f"\n导入完成！")
    print(f"  总数据行: {total}")
    print(f"  新建稿件: {created_submissions}")
    print(f"  新建派稿: {created_assignments}")
    print(f"  新建编辑: {created_authors}")
    print(f"  跳过: {skipped}")
    if errors:
        print(f"\n错误 ({len(errors)}):")
        for e in errors[:10]:
            print(f"  {e}")
        if len(errors) > 10:
            print(f"  ... 还有 {len(errors)-10} 个错误")

if __name__ == "__main__":
    main()
