from __future__ import annotations

import email
import imaplib
from email.header import decode_header, make_header
from email.message import Message
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .config import AppConfig
from .models import AttachmentData
from .utils import extract_docx_text_from_bytes, normalize_whitespace


def decode_mime_header(value: Optional[str]) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def extract_body_text(message: Message) -> str:
    if message.is_multipart():
        parts: List[str] = []
        for part in message.walk():
            content_disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" in content_disposition:
                continue
            if part.get_content_type() in {"text/plain", "text/html"}:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                try:
                    text = payload.decode(charset, errors="ignore")
                except LookupError:
                    text = payload.decode("utf-8", errors="ignore")
                parts.append(text)
        return normalize_whitespace("\n".join(parts))
    payload = message.get_payload(decode=True) or b""
    charset = message.get_content_charset() or "utf-8"
    try:
        return normalize_whitespace(payload.decode(charset, errors="ignore"))
    except LookupError:
        return normalize_whitespace(payload.decode("utf-8", errors="ignore"))


def extract_attachments(message: Message) -> List[AttachmentData]:
    attachments: List[AttachmentData] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        content_disposition = (part.get("Content-Disposition") or "").lower()
        filename = decode_mime_header(part.get_filename())
        if "attachment" not in content_disposition and not filename:
            continue
        payload = part.get_payload(decode=True) or b""
        content_type = part.get_content_type()
        extracted_text = ""
        if filename.lower().endswith(".docx"):
            try:
                extracted_text = extract_docx_text_from_bytes(payload)
            except Exception:
                extracted_text = ""
        attachments.append(
            AttachmentData(
                filename=filename or "未命名附件",
                content_type=content_type,
                payload=payload,
                extracted_text=extracted_text,
            )
        )
    return attachments


def fetch_messages_from_imap(
    config: AppConfig,
    after_uid: Optional[str] = None,
    limit: Optional[int] = None,
) -> Iterable[Tuple[str, bytes]]:
    mailbox = config.mailbox
    client = imaplib.IMAP4_SSL(mailbox.imap_host, mailbox.imap_port)
    try:
        client.login(mailbox.username, mailbox.password)
        # 必须检查 select 返回值，避免停留在 AUTH 状态
        status, _ = client.select(mailbox.folder)
        if status != "OK":
            raise RuntimeError(
                f"无法选择邮箱文件夹「{mailbox.folder}」，服务器返回状态：{status}"
            )
        query = f"(UID {int(after_uid) + 1}:*)" if after_uid else "ALL"
        typ, data = client.uid("search", None, query)
        if typ != "OK":
            return []
        uids = [item.decode("utf-8") for item in data[0].split() if item]
        if limit:
            uids = uids[-limit:]
        results = []
        for uid in uids:
            typ, fetched = client.uid("fetch", uid, "(RFC822)")
            if typ != "OK" or not fetched:
                continue
            raw = fetched[0][1]
            results.append((uid, raw))
        return results
    finally:
        try:
            client.close()
        except Exception:
            pass
        client.logout()


def load_messages_from_eml_dir(directory: Path) -> Iterable[Tuple[str, bytes]]:
    items = []
    for index, path in enumerate(sorted(directory.glob("*.eml")), start=1):
        items.append((str(index), path.read_bytes()))
    return items


def is_submission_email(message: Message) -> bool:
    """判断一封邮件是否为投稿邮件（过滤系统通知、回复等无效邮件）。"""
    sender = message.get("From", "")
    subject = decode_mime_header(message.get("Subject", ""))

    # 跳过系统/通知类发件人
    system_senders = [
        "no-reply@", "notification@", "safe@", "pageupdates@",
        "facebookmail.com", "google.com", "notifications.google.com",
    ]
    if any(p in sender for p in system_senders):
        return False

    # 投稿应有附件（至少一篇稿件文档）
    attachments = extract_attachments(message)
    if not attachments:
        return False

    # 跳过纯回复/转发链（不含投稿标记）
    # 注：不跳过有投稿标记的回复（如"【定稿】"、"【录用通知】"）
    is_reply = any(
        subject.startswith(prefix) for prefix in ["Re:", "回复：", "回复:", "回複："]
    )
    submission_markers = ["【定稿】", "【录用", "【一审", "【二审", "【三审"]
    has_marker = any(m in subject for m in submission_markers)
    if is_reply and not has_marker:
        return False

    return True


def parse_message(raw: bytes) -> Message:
    return email.message_from_bytes(raw)

def fetch_messages_from_pop3(
    config: AppConfig,
    limit: Optional[int] = None,
) -> Iterable[Tuple[str, bytes]]:
    """用 POP3 从 126 邮箱抓取最新邮件（替代 IMAP 的降级方案）"""
    import poplib
    mailbox = config.mailbox
    client = poplib.POP3_SSL("pop.126.com", 995)
    try:
        client.user(mailbox.username)
        client.pass_(mailbox.password)
        num_messages = len(client.list()[1])
        if num_messages == 0:
            return []
        # 若有限制，只取最新的 limit 封
        start = max(1, num_messages - limit + 1) if limit else 1
        end = num_messages
        results = []
        for i in range(end, start - 1, -1):  # 从最新倒序
            response = client.retr(i)
            raw_email = b"\r\n".join(response[1])
            uid = str(i)  # POP3 没有 UID，用邮件序号代替
            results.append((uid, raw_email))
        return results
    finally:
        client.quit()