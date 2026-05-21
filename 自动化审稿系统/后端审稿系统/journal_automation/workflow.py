from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .config import AppConfig
from .mail import (
    fetch_messages_from_imap,
    fetch_messages_from_pop3,
    is_submission_email,
    load_messages_from_eml_dir,
    parse_message,
)
from .metadata import parse_submission
from .models import DraftContext
from .state import StateStore
from .storage import (
    archive_submission_attachments,
    copy_manuscript_to_stage,
    create_stage_folder,
    save_raw_message,
)
from .templates import build_draft_eml, create_review_form, default_review_form_name
from .workbook import append_progress_note, append_submission, find_duplicate_title

PROGRESS_COLUMN_MAP = {
    "一审退稿": "一审编辑及审稿情况",
    "一审返修": "一审编辑及审稿情况",
    "一审通过": "一审编辑及审稿情况",
    "二审退稿": "二审编辑及审稿情况",
    "二审返修": "二审编辑及审稿情况",
    "二审通过": "二审编辑及审稿情况",
    "三审退稿": "再审情况",
    "三审返修": "再审情况",
    "三审通过": "再审情况",
    "录用定稿": "组内终审情况及拟排期",
}


def sync_submissions(
    config: AppConfig, eml_dir: Optional[Path] = None, limit: Optional[int] = None
) -> dict:
    state = StateStore(config.runtime.database)
    try:
        raw_messages: Iterable[tuple[str, bytes]]
        if eml_dir:
            raw_messages = load_messages_from_eml_dir(eml_dir)
        else:
            # 优先使用 IMAP（通过 ID 命令满足 126 安全检查），失败时回退到 POP3
            last_uid = state.get_last_uid()
            try:
                raw_messages = fetch_messages_from_imap(config, after_uid=last_uid, limit=limit)
            except Exception as imap_err:
                print(f"IMAP 连接失败: {imap_err}，尝试 POP3 回退...")
                raw_messages = fetch_messages_from_pop3(config, limit=limit)

        summary = {"created": 0, "skipped": 0, "manual_review": 0}
        last_uid: Optional[str] = None
        for uid, raw in raw_messages:
            message = parse_message(raw)
            # 跳过非投稿邮件（系统通知、回复链等）
            if not is_submission_email(message):
                summary["skipped"] += 1
                continue
            message_id = message.get("Message-ID") or f"<local-{uid}>"
            if state.get_submission_by_message_id(message_id):
                summary["skipped"] += 1
                last_uid = uid
                continue
            record, attachments = parse_submission(message_id, uid, message, config)
            save_raw_message(config, message_id, raw)
            if record.title:
                record.duplicate_warning = find_duplicate_title(
                    config.workbook, record.title
                )
            main_path, saved_paths = archive_submission_attachments(
                config, record, attachments
            )
            record.manuscript_path = main_path
            record.attachment_paths = saved_paths
            row_number = append_submission(config.workbook, record)
            record.workbook_row = row_number
            record_id = state.save_submission(record)
            state.update_record_paths(
                record_id,
                str(main_path) if main_path else "",
                [str(item) for item in saved_paths],
                row_number,
            )
            if record.needs_manual_review:
                write_issue(config, record_id, record)
                summary["manual_review"] += 1
            summary["created"] += 1
            last_uid = uid
        if last_uid:
            state.set_last_uid(last_uid)
        return summary
    finally:
        state.close()


def write_issue(config: AppConfig, record_id: int, record) -> Path:
    payload = {
        "record_id": record_id,
        "title": record.title,
        "discipline": record.discipline,
        "authors": record.authors,
        "message_id": record.message_id,
        "reason": "待人工确认",
        "needs_anonymization_check": record.needs_anonymization_check,
    }
    path = config.runtime.issue_dir / f"{record_id:04d}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def prepare_reply_package(
    config: AppConfig,
    record_id: int,
    result_label: str,
    editor_name: str,
    folder_date: Optional[str] = None,
    expected_issue: str = "",
    deadline_days: int = 14,
) -> dict:
    state = StateStore(config.runtime.database)
    try:
        row = state.get_submission(record_id)
        if not row:
            raise ValueError(f"未找到 record_id={record_id}")
        record = row_to_submission(row)
        folder_date = folder_date or datetime.now().strftime("%Y%m%d")
        stage_folder = create_stage_folder(config, folder_date, result_label, record)
        attachments = []
        manuscript_copy = copy_manuscript_to_stage(record, stage_folder)
        if manuscript_copy:
            attachments.append(manuscript_copy)
        review_form_path = stage_folder / default_review_form_name(record)
        create_review_form(
            config.templates.review_form,
            review_form_path,
            record.title,
            "、".join(record.authors) if record.authors else "待补充",
            editor_name,
        )
        attachments.append(review_form_path)
        draft_path = (
            config.runtime.draft_dir / f"{folder_date}-{record_id}-{result_label}.eml"
        )
        context = DraftContext(
            record_id=record_id,
            result_label=result_label,
            stage_name=result_label,
            editor_name=editor_name,
            folder_date=folder_date,
            author_display=record.authors[0] if record.authors else "作者",
            attachments=attachments,
            expected_issue=expected_issue,
            deadline_days=deadline_days,
        )
        build_draft_eml(config, record, context, draft_path)
        state.update_stage(record_id, result_label, str(stage_folder), str(draft_path))
        return {
            "stage_folder": str(stage_folder),
            "draft_path": str(draft_path),
            "attachments": [str(item) for item in attachments],
            "recommended_editors": config.editors_by_subject.get(
                record.discipline, []
            ),
        }
    finally:
        state.close()


def update_progress(
    config: AppConfig,
    record_id: int,
    result_label: str,
    editor_name: str,
    note_date: Optional[str] = None,
    expected_issue: str = "",
) -> str:
    state = StateStore(config.runtime.database)
    try:
        row = state.get_submission(record_id)
        if not row:
            raise ValueError(f"未找到 record_id={record_id}")
        if not row["workbook_row"]:
            raise ValueError("该记录尚未写入总表")
        column = PROGRESS_COLUMN_MAP[result_label]
        note_date = note_date or datetime.now().strftime("%Y.%m.%d")
        # 规范化进度文本
        if result_label == "录用定稿":
            suffix = f"{note_date}通过（{editor_name}）"
            if expected_issue:
                suffix += f"\n{expected_issue}"
        else:
            # 去掉一二三审，保留“返修”“退稿”等结论
            short_stage = (
                result_label.replace("一审", "")
                .replace("二审", "")
                .replace("三审", "")
            )
            suffix = f"{note_date}{short_stage}（{editor_name}）"
        append_progress_note(config.workbook, int(row["workbook_row"]), column, suffix)
        state.update_stage(record_id, result_label)
        return suffix
    finally:
        state.close()


def row_to_submission(row) -> "SubmissionRecord":
    from .models import SubmissionRecord  # noqa: F811

    return SubmissionRecord(
        message_id=row["message_id"],
        uid=row["uid"],
        subject_line=row["subject_line"],
        sender=row["sender"],
        sender_name=row["sender_name"],
        sent_at=row["sent_at"],
        title=row["title"],
        discipline=row["discipline"],
        authors=json.loads(row["authors_json"] or "[]"),
        author_info=row["author_info"] or "",
        contact_info=row["contact_info"] or "",
        body_text=row["body_text"] or "",
        status=row["status"] or "未处理",
        needs_manual_review=bool(row["needs_manual_review"]),
        needs_anonymization_check=bool(row["needs_anonymization_check"]),
        duplicate_warning=bool(row["duplicate_warning"]),
        main_attachment_name=row["main_attachment_name"] or "",
        manuscript_path=Path(row["manuscript_path"]) if row["manuscript_path"] else None,
        attachment_paths=[
            Path(item) for item in json.loads(row["attachment_paths_json"] or "[]")
        ],
        workbook_row=row["workbook_row"],
    )