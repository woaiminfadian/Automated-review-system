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

        # ---------- 关键修复：用 raw socket 发送正确的 ID 命令 ----------
        try:
            # 向服务器标识自己为“PythonMailClient”
            client.send(b'ID ("name" "PythonMailClient" "version" "1.0")\r\n')
            # 读取一行响应（通常形如 * ID ("name" "..." ...)）
            response = client.readline()
            print(f"ID 命令响应: {response}")  # 调试用，正式版可注释掉
            # 读取命令完成标记（如 OK ID completed）
            status_line = client.readline()
            print(f"ID 状态: {status_line}")
        except Exception as e:
            print(f"发送 ID 时出错: {e}")

        status, data = client.select(mailbox.folder, readonly=True)
        if status != "OK":
            # 把服务器返回的详细信息一并报出，方便定位原因
            detail = data[0].decode() if data else "无详情"
            raise RuntimeError(
                f"无法选择邮箱文件夹「{mailbox.folder}」，服务器返回状态：{status}，详细信息：{detail}"
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


def parse_message(raw: bytes) -> Message:
    return email.message_from_bytes(raw)