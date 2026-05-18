from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class MailboxConfig:
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    folder: str


@dataclass
class TemplateConfig:
    review_form: Path
    law_reply: Path
    non_law_reply: Path
    copyright_agreement: Path


@dataclass
class RuntimeConfig:
    state_dir: Path
    raw_mail_dir: Path
    draft_dir: Path
    issue_dir: Path
    database: Path


@dataclass
class AppConfig:
    root_dir: Path
    mailbox: MailboxConfig
    templates: TemplateConfig
    runtime: RuntimeConfig
    workbook: Path
    editors_by_subject: Dict[str, List[str]]
    non_law_subjects: List[str]
    subject_aliases: Dict[str, List[str]]
    preferred_extensions: List[str]


def _resolve_path(root_dir: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (root_dir / path)


def load_config(path: Path) -> AppConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    root_dir = _resolve_path(path.parent, data["root_dir"]).resolve()

    runtime_root = _resolve_path(root_dir, data["runtime"]["state_dir"]).resolve()
    runtime = RuntimeConfig(
        state_dir=runtime_root,
        raw_mail_dir=runtime_root / "raw_mail",
        draft_dir=runtime_root / "drafts",
        issue_dir=runtime_root / "issues",
        database=runtime_root / "journal_automation.sqlite3",
    )

    mailbox = MailboxConfig(**data["mailbox"])
    templates = TemplateConfig(
        review_form=_resolve_path(root_dir, data["templates"]["review_form"]),
        law_reply=_resolve_path(root_dir, data["templates"]["law_reply"]),
        non_law_reply=_resolve_path(root_dir, data["templates"]["non_law_reply"]),
        copyright_agreement=_resolve_path(root_dir, data["templates"]["copyright_agreement"]),
    )
    app = AppConfig(
        root_dir=root_dir,
        mailbox=mailbox,
        templates=templates,
        runtime=runtime,
        workbook=_resolve_path(root_dir, data["workbook"]),
        editors_by_subject=data["editors_by_subject"],
        non_law_subjects=data["non_law_subjects"],
        subject_aliases=data["subject_aliases"],
        preferred_extensions=data.get("preferred_extensions", [".docx", ".doc", ".pdf"]),
    )
    ensure_runtime_dirs(app)
    return app


def ensure_runtime_dirs(config: AppConfig) -> None:
    for path in [
        config.runtime.state_dir,
        config.runtime.raw_mail_dir,
        config.runtime.draft_dir,
        config.runtime.issue_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def find_default_config(root_dir: Path) -> Optional[Path]:
    candidate = root_dir / "automation.config.json"
    return candidate if candidate.exists() else None
