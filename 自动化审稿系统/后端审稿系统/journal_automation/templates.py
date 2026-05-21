from __future__ import annotations

import logging
import re
import zipfile
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List
from xml.sax.saxutils import escape

from .config import AppConfig
from .models import DraftContext, SubmissionRecord
from .utils import extract_docx_text, sanitize_filename

logger = logging.getLogger(__name__)


SECTION_MAP = {
    "一审退稿": "初审未通过",
    "一审返修": "初审通过",
    "二审退稿": "复审未通过",
    "三审退稿": "复审未通过",
    "外审退稿": "复审未通过",
    "二审返修": "复审仍需修改",
    "三审返修": "复审仍需修改",
    "外审返修": "复审仍需修改",
    "二审通过": "复审通过",
    "三审通过": "复审通过",
    "外审通过": "复审通过",
    "录用定稿": "组内评审会通过",
}


def parse_reply_template(path: Path) -> Dict[str, str]:
    text = extract_docx_text(path)
    pattern = re.compile(
        r"([一二三四五六七八九十]+、(?:初审未通过|初审未通过意识形态审核|初审通过|复审未通过|复审仍需修改|复审通过|组内评审会通过|出版社质量检查及返修))[:：]\s*"
    )
    matches = list(pattern.finditer(text))
    sections: Dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1).split("、", 1)[1]
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[title] = text[start:end].strip()
    return sections


def build_reply_body(config: AppConfig, record: SubmissionRecord, result_label: str, deadline_days: int, expected_issue: str) -> str:
    is_non_law = record.discipline in config.non_law_subjects
    template_path = config.templates.non_law_reply if is_non_law else config.templates.law_reply
    sections = parse_reply_template(template_path)
    section_title = SECTION_MAP[result_label]
    body = sections.get(section_title, "").strip()
    author_name = record.authors[0] if record.authors else "作者"
    body = body.replace("尊敬的作者：", f"{author_name}老师：")
    body = body.replace("两周", f"{deadline_days}天")
    if expected_issue:
        body += f"\n\n拟安排期次：{expected_issue}"
    return body


def create_review_form(template_path: Path, output_path: Path, title: str, author_text: str, editor_name: str) -> Path:
    replacements = {
        "论文题目：</w:t></w:r></w:p>": f"论文题目：</w:t></w:r><w:r><w:rPr><w:rFonts w:hint=\"eastAsia\"/><w:sz w:val=\"24\"/></w:rPr><w:t>{escape(title)}</w:t></w:r></w:p>",
        "论文作者：</w:t></w:r><w:r><w:rPr><w:rFonts w:hint=\"eastAsia\"/><w:sz w:val=\"24\"/></w:rPr><w:t xml:space=\"preserve\">                                  </w:t></w:r>": f"论文作者：</w:t></w:r><w:r><w:rPr><w:rFonts w:hint=\"eastAsia\"/><w:sz w:val=\"24\"/></w:rPr><w:t xml:space=\"preserve\"> {escape(author_text)}</w:t></w:r>",
        "学生编辑：</w:t></w:r><w:r><w:rPr><w:rFonts w:hint=\"eastAsia\"/><w:sz w:val=\"24\"/></w:rPr><w:t xml:space=\"preserve\"> </w:t></w:r></w:p>": f"学生编辑：</w:t></w:r><w:r><w:rPr><w:rFonts w:hint=\"eastAsia\"/><w:sz w:val=\"24\"/></w:rPr><w:t xml:space=\"preserve\"> {escape(editor_name)}</w:t></w:r></w:p>",
    }

    with zipfile.ZipFile(template_path) as source, zipfile.ZipFile(output_path, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "word/document.xml":
                text = data.decode("utf-8")
                missing = []
                for old, new in replacements.items():
                    if old not in text:
                        missing.append(old)
                    text = text.replace(old, new, 1)
                if missing:
                    logger.warning(
                        "create_review_form: %d/%d placeholder(s) not found in template %s",
                        len(missing), len(replacements), template_path
                    )
                data = text.encode("utf-8")
            target.writestr(info, data)
    return output_path


def build_draft_eml(
    config: AppConfig,
    record: SubmissionRecord,
    context: DraftContext,
    output_path: Path,
) -> Path:
    msg = EmailMessage()
    msg["Subject"] = f"《中国政法大学研究生学报》{context.result_label}通知：{record.title}"
    msg["To"] = record.sender
    msg["From"] = config.mailbox.username
    msg["X-Codex-Draft"] = "true"
    msg.set_content(build_reply_body(config, record, context.result_label, context.deadline_days, context.expected_issue))
    for attachment_path in context.attachments:
        if not attachment_path.exists():
            continue
        data = attachment_path.read_bytes()
        msg.add_attachment(
            data,
            maintype="application",
            subtype="octet-stream",
            filename=attachment_path.name,
        )
    output_path.write_bytes(msg.as_bytes())
    return output_path


def default_review_form_name(record: SubmissionRecord) -> str:
    title = sanitize_filename(record.title)
    return f"审稿评分表 {title}.docx"
