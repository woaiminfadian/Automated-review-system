from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from .models import SubmissionRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE NOT NULL,
    uid TEXT,
    subject_line TEXT,
    sender TEXT,
    sender_name TEXT,
    sent_at TEXT,
    title TEXT,
    discipline TEXT,
    authors_json TEXT,
    author_info TEXT,
    contact_info TEXT,
    body_text TEXT,
    status TEXT,
    needs_manual_review INTEGER,
    needs_anonymization_check INTEGER,
    duplicate_warning INTEGER,
    main_attachment_name TEXT,
    manuscript_path TEXT,
    attachment_paths_json TEXT,
    workbook_row INTEGER,
    stage_folder TEXT,
    draft_path TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def get_last_uid(self) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM sync_state WHERE key = 'last_uid'").fetchone()
        return row["value"] if row else None

    def set_last_uid(self, value: str) -> None:
        self.conn.execute(
            "INSERT INTO sync_state(key, value) VALUES('last_uid', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (value,),
        )
        self.conn.commit()

    def get_submission_by_message_id(self, message_id: str):
        return self.conn.execute("SELECT * FROM submissions WHERE message_id = ?", (message_id,)).fetchone()

    def get_submission(self, record_id: int):
        return self.conn.execute("SELECT * FROM submissions WHERE id = ?", (record_id,)).fetchone()

    def list_pending(self) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM submissions WHERE needs_manual_review = 1 OR status = '未处理' ORDER BY id DESC"
        ).fetchall()

    def save_submission(self, record: SubmissionRecord) -> int:
        existing = self.get_submission_by_message_id(record.message_id)
        payload = (
            record.uid,
            record.subject_line,
            record.sender,
            record.sender_name,
            record.sent_at,
            record.title,
            record.discipline,
            json.dumps(record.authors, ensure_ascii=False),
            record.author_info,
            record.contact_info,
            record.body_text,
            record.status,
            int(record.needs_manual_review),
            int(record.needs_anonymization_check),
            int(record.duplicate_warning),
            record.main_attachment_name,
            str(record.manuscript_path) if record.manuscript_path else "",
            json.dumps([str(item) for item in record.attachment_paths], ensure_ascii=False),
            record.workbook_row,
            record.message_id,
        )
        if existing:
            self.conn.execute(
                """
                UPDATE submissions
                SET uid=?, subject_line=?, sender=?, sender_name=?, sent_at=?, title=?, discipline=?, authors_json=?,
                    author_info=?, contact_info=?, body_text=?, status=?, needs_manual_review=?, needs_anonymization_check=?,
                    duplicate_warning=?, main_attachment_name=?, manuscript_path=?, attachment_paths_json=?, workbook_row=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE message_id=?
                """,
                payload,
            )
            self.conn.commit()
            return int(existing["id"])
        cursor = self.conn.execute(
            """
            INSERT INTO submissions(
                uid, subject_line, sender, sender_name, sent_at, title, discipline, authors_json, author_info,
                contact_info, body_text, status, needs_manual_review, needs_anonymization_check, duplicate_warning,
                main_attachment_name, manuscript_path, attachment_paths_json, workbook_row, message_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_record_paths(self, record_id: int, manuscript_path: str, attachment_paths: List[str], workbook_row: Optional[int]) -> None:
        self.conn.execute(
            """
            UPDATE submissions
            SET manuscript_path=?, attachment_paths_json=?, workbook_row=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (manuscript_path, json.dumps(attachment_paths, ensure_ascii=False), workbook_row, record_id),
        )
        self.conn.commit()

    def update_stage(self, record_id: int, status: str, stage_folder: Optional[str] = None, draft_path: Optional[str] = None) -> None:
        self.conn.execute(
            """
            UPDATE submissions
            SET status=?, stage_folder=COALESCE(?, stage_folder), draft_path=COALESCE(?, draft_path), updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (status, stage_folder, draft_path, record_id),
        )
        self.conn.commit()

