from __future__ import annotations

import re
from email.utils import parseaddr, parsedate_to_datetime
from typing import Dict, Iterable, List, Optional, Tuple

from .config import AppConfig
from .mail import decode_mime_header, extract_attachments, extract_body_text
from .models import AttachmentData, SubmissionRecord
from .utils import chunked_lines, normalize_whitespace, sanitize_filename


TITLE_PATTERNS = [
    r"(?:论文题目|稿件题目|文章题目|题目)[:：]\s*[《“\"]?(.+?)[》”\"]?(?:\n|$)",
    r"(?:投稿题目|来稿题目)[:：]\s*[《“\"]?(.+?)[》”\"]?(?:\n|$)",
]
AUTHOR_PATTERNS = [
    r"(?:作者|第一作者|姓名)[:：]\s*([^\n，,；;]+)",
]
AUTHOR_INFO_PATTERNS = [
    r"(?:学校|院校|单位|学院|专业|年级|学历|方向)[:：].+",
]
CONTACT_PATTERNS = [
    r"(?:联系电话|电话|手机)[:：]?\s*([0-9\-+ ]{7,})",
    r"(?:电子邮箱|邮箱|E-mail|Email)[:：]?\s*([A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+)",
    r"(?:通讯地址|邮寄地址|联系地址|收件地址及邮编)[:：].+",
]


def parse_submission(message_id: str, uid: Optional[str], message, config: AppConfig) -> Tuple[SubmissionRecord, List[AttachmentData]]:
    subject_line = decode_mime_header(message.get("Subject"))
    sender_name, sender_addr = parseaddr(decode_mime_header(message.get("From")))
    body_text = extract_body_text(message)
    attachments = extract_attachments(message)
    reference_text = "\n".join([subject_line, body_text] + [item.filename for item in attachments] + [item.extracted_text[:2000] for item in attachments if item.extracted_text])

    title = detect_title(subject_line, body_text, attachments)
    discipline, discipline_confident = detect_discipline(reference_text, config)
    if title and discipline != "待确认":
        prefix = discipline + "-"
        if title.startswith(prefix):
            title = title[len(prefix):].strip()
        cn_prefix = discipline + "－"
        if title.startswith(cn_prefix):
            title = title[len(cn_prefix):].strip()
    authors = detect_authors(body_text, attachments, sender_name)
    author_info = detect_author_info(body_text, attachments)
    contact_info = detect_contact_info(body_text, attachments, sender_addr)
    sent_at = ""
    if message.get("Date"):
        try:
            sent_at = parsedate_to_datetime(message.get("Date")).strftime("%Y.%m.%d")
        except Exception:
            sent_at = ""

    main_attachment = choose_main_attachment(attachments, config.preferred_extensions)
    needs_anonymization_check = detect_non_anonymous(main_attachment, authors, author_info)

    record = SubmissionRecord(
        message_id=message_id,
        uid=uid,
        subject_line=subject_line,
        sender=sender_addr,
        sender_name=sender_name,
        sent_at=sent_at,
        title=title,
        discipline=discipline,
        authors=authors,
        author_info=author_info,
        contact_info=contact_info,
        body_text=body_text,
        needs_manual_review=not discipline_confident or not title,
        needs_anonymization_check=needs_anonymization_check,
        main_attachment_name=main_attachment.filename if main_attachment else "",
    )
    classify_attachments(attachments, main_attachment)
    return record, attachments


def detect_title(subject_line: str, body_text: str, attachments: List[AttachmentData]) -> str:
    text = "\n".join([subject_line, body_text] + [item.extracted_text[:1000] for item in attachments if item.extracted_text])
    for pattern in TITLE_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return sanitize_filename(clean_title(match.group(1)))
    subject_guess = subject_line
    subject_guess = re.sub(r"^(?:投稿|来稿|论文|稿件)[：:\s-]*", "", subject_guess)
    subject_guess = re.sub(r"(?:投稿|请审阅|烦请查收).*$", "", subject_guess)
    subject_guess = clean_title(subject_guess)
    if len(subject_guess) >= 4:
        return sanitize_filename(subject_guess)
    for item in attachments:
        if item.filename:
            name = sanitize_filename(re.sub(r"\.[^.]+$", "", item.filename))
            if len(name) >= 4:
                return name
    return ""


def clean_title(title: str) -> str:
    title = normalize_whitespace(title)
    title = title.strip("《》“”\"' ")
    return title


def detect_discipline(text: str, config: AppConfig) -> Tuple[str, bool]:
    condensed = normalize_whitespace(text)
    for discipline, aliases in config.subject_aliases.items():
        for alias in [discipline] + aliases:
            if alias and alias in condensed:
                return discipline, True
    title = extract_possible_title_line(condensed)
    for discipline, aliases in config.subject_aliases.items():
        for alias in [discipline] + aliases:
            if alias and alias in title:
                return discipline, True
    return "待确认", False


def extract_possible_title_line(text: str) -> str:
    for line in chunked_lines(text):
        if 6 <= len(line) <= 80:
            return line
    return text[:80]


def is_valid_author_name(name: str) -> bool:
    """判断名字是否像真实作者姓名（过滤手机号、邮箱、乱码）。"""
    if not name or len(name) < 2 or len(name) > 20:
        return False
    # 纯数字或含 +86 的手机号
    if re.match(r'^\+?\d[\d\- ]{6,}$', name):
        return False
    # 包含 @ 符号
    if "@" in name:
        return False
    # 数字占比超过 40%（如"生Zi当如孙仲谋"→数字0%，但含字母的乱码名会通过）
    digits = sum(1 for c in name if c.isdigit())
    if digits > 0 and digits > len(name) * 0.4:
        return False
    return True


def detect_authors(body_text: str, attachments: List[AttachmentData], sender_name: str) -> List[str]:
    pool = "\n".join([body_text] + [item.extracted_text[:2000] for item in attachments if item.extracted_text])
    authors: List[str] = []
    for pattern in AUTHOR_PATTERNS:
        for match in re.finditer(pattern, pool, flags=re.IGNORECASE):
            candidate = normalize_whitespace(match.group(1)).strip("，,；; ")
            if is_valid_author_name(candidate) and candidate not in authors:
                authors.append(candidate)
    if not authors and sender_name:
        cleaned = normalize_whitespace(sender_name)
        if is_valid_author_name(cleaned):
            authors.append(cleaned)
    return authors[:2]


def detect_author_info(body_text: str, attachments: List[AttachmentData]) -> str:
    lines: List[str] = []
    pool_lines = list(chunked_lines(body_text))
    for item in attachments:
        pool_lines.extend(chunked_lines(item.extracted_text[:3000]))
    for line in pool_lines:
        if any(keyword in line for keyword in ["大学", "学院", "研究生", "专业", "年级", "方向"]):
            if line not in lines:
                lines.append(line)
    return "\n".join(lines[:4])


def detect_contact_info(body_text: str, attachments: List[AttachmentData], sender_addr: str) -> str:
    pool = "\n".join([body_text] + [item.extracted_text[:2000] for item in attachments if item.extracted_text])
    lines: List[str] = []
    for pattern in CONTACT_PATTERNS:
        for match in re.finditer(pattern, pool, flags=re.IGNORECASE):
            value = normalize_whitespace(match.group(0))
            if value not in lines:
                lines.append(value)
    if sender_addr and not any("@" in line for line in lines):
        lines.append("电子邮箱：" + sender_addr)
    return "\n".join(lines[:5])


def choose_main_attachment(attachments: List[AttachmentData], preferred_extensions: Iterable[str]) -> Optional[AttachmentData]:
    ranked: List[Tuple[int, AttachmentData]] = []
    normalized_preferred = [item.lower() for item in preferred_extensions]
    for attachment in attachments:
        filename = attachment.filename.lower()
        score = 0
        for index, ext in enumerate(normalized_preferred):
            if filename.endswith(ext):
                score += 100 - index * 10
        if any(keyword in filename for keyword in ["投稿", "论文", "稿件", "正文"]):
            score += 20
        if any(keyword in filename for keyword in ["版权", "协议", "简历", "查重", "修改说明"]):
            score -= 25
        ranked.append((score, attachment))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def classify_attachments(attachments: List[AttachmentData], main_attachment: Optional[AttachmentData]) -> None:
    for attachment in attachments:
        if main_attachment and attachment.filename == main_attachment.filename:
            attachment.category = "manuscript"
        elif any(keyword in attachment.filename for keyword in ["版权", "协议"]):
            attachment.category = "agreement"
        else:
            attachment.category = "supplement"


def detect_non_anonymous(attachment: Optional[AttachmentData], authors: List[str], author_info: str) -> bool:
    if not attachment or not attachment.extracted_text:
        return False
    sample = attachment.extracted_text[:4000]
    for author in authors:
        if author and author in sample:
            return True
    for token in ["大学", "学院", "作者简介", "作者："]:
        if token in sample and author_info:
            return True
    return False
