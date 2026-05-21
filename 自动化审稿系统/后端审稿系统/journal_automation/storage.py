from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from .config import AppConfig
from .models import AttachmentData, SubmissionRecord
from .utils import ensure_unique_path, sanitize_filename


def save_raw_message(config: AppConfig, message_id: str, raw: bytes) -> Path:
    safe_name = sanitize_filename(message_id.replace("<", "").replace(">", ""), "message")
    path = ensure_unique_path(config.runtime.raw_mail_dir / f"{safe_name}.eml")
    path.write_bytes(raw)
    return path


def archive_submission_attachments(
    config: AppConfig,
    record: SubmissionRecord,
    attachments: List[AttachmentData],
) -> Tuple[Optional[Path], List[Path]]:
    target_dir = config.root_dir / "1. 未处理来稿"
    title = sanitize_filename(record.title or "待确认题目")
    discipline = sanitize_filename(record.discipline or "待确认")
    main_path: Optional[Path] = None
    saved_paths: List[Path] = []

    for index, attachment in enumerate(attachments, start=1):
        suffix = Path(attachment.filename).suffix or ".bin"
        if attachment.category == "manuscript":
            base_name = f"{discipline}-{title}"
        elif attachment.category == "agreement":
            base_name = f"{discipline}-{title}-著作权协议"
        else:
            original = sanitize_filename(Path(attachment.filename).stem, f"附件{index}")
            base_name = f"{discipline}-{title}-附件{index}-{original}"
        destination = ensure_unique_path(target_dir / f"{base_name}{suffix}")
        destination.write_bytes(attachment.payload)
        saved_paths.append(destination)
        if attachment.category == "manuscript":
            main_path = destination
    return main_path, saved_paths


def create_stage_folder(config: AppConfig, folder_date: str, result_label: str, record: SubmissionRecord) -> Path:
    stage_root = config.root_dir / "2. 派稿及回复" / folder_date
    stage_root.mkdir(parents=True, exist_ok=True)
    author = sanitize_filename("、".join(record.authors) if record.authors else "待确认作者")
    discipline = sanitize_filename(record.discipline or "待确认")
    title = sanitize_filename(record.title or "待确认题目")
    folder_name = f"【{result_label}】{discipline}-{author}-{title}"
    folder = ensure_unique_path(stage_root / folder_name)
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def copy_manuscript_to_stage(record: SubmissionRecord, stage_folder: Path) -> Optional[Path]:
    if not record.manuscript_path:
        return None
    source = Path(record.manuscript_path)
    destination = stage_folder / source.name
    if source.exists():
        shutil.copy2(source, destination)
        return destination
    return None

