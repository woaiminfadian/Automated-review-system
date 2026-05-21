from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class AttachmentData:
    filename: str
    content_type: str
    payload: bytes
    extracted_text: str = ""
    category: str = "supplement"


@dataclass
class SubmissionRecord:
    message_id: str
    uid: Optional[str]
    subject_line: str
    sender: str
    sender_name: str
    sent_at: str
    title: str
    discipline: str
    authors: List[str] = field(default_factory=list)
    author_info: str = ""
    contact_info: str = ""
    body_text: str = ""
    status: str = "未处理"
    needs_manual_review: bool = False
    needs_anonymization_check: bool = False
    duplicate_warning: bool = False
    main_attachment_name: str = ""
    manuscript_path: Optional[Path] = None
    attachment_paths: List[Path] = field(default_factory=list)
    workbook_row: Optional[int] = None


@dataclass
class DraftContext:
    record_id: int
    result_label: str
    stage_name: str
    editor_name: str
    folder_date: str
    author_display: str
    attachments: List[Path]
    expected_issue: str = ""
    deadline_days: int = 14

