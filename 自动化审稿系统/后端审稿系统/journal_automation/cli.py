from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import find_default_config, load_config
from .state import StateStore
from .workflow import prepare_reply_package, sync_submissions, update_progress


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="126 投稿自动处理工具")
    parser.add_argument("--config", type=Path, default=None, help="配置文件路径")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync-submissions", help="同步投稿邮件")
    sync_parser.add_argument("--eml-dir", type=Path, help="从本地 .eml 目录导入")
    sync_parser.add_argument("--limit", type=int, help="仅处理最新 N 封邮件")

    prepare_parser = subparsers.add_parser("generate-reply-materials", help="生成派稿/回复材料")
    prepare_parser.add_argument("--record-id", type=int, required=True)
    prepare_parser.add_argument("--result-label", required=True, help="例如 一审返修 / 一审退稿 / 录用定稿")
    prepare_parser.add_argument("--editor-name", required=True)
    prepare_parser.add_argument("--folder-date", help="目录日期，格式 YYYYMMDD")
    prepare_parser.add_argument("--expected-issue", default="", help="拟安排期次")
    prepare_parser.add_argument("--deadline-days", type=int, default=14)

    progress_parser = subparsers.add_parser("update-progress", help="更新总表进度")
    progress_parser.add_argument("--record-id", type=int, required=True)
    progress_parser.add_argument("--result-label", required=True)
    progress_parser.add_argument("--editor-name", required=True)
    progress_parser.add_argument("--note-date", help="格式 YYYY.MM.DD")
    progress_parser.add_argument("--expected-issue", default="")

    subparsers.add_parser("list-pending", help="查看待确认稿件")
    return parser


def resolve_config_path(cli_path: Path | None) -> Path:
    if cli_path:
        return cli_path
    default = find_default_config(Path.cwd())
    if not default:
        raise FileNotFoundError("未找到配置文件，请在工作目录中创建 automation.config.json，或通过 --config 指定。")
    return default


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(resolve_config_path(args.config))

    if args.command == "sync-submissions":
        result = sync_submissions(config, eml_dir=args.eml_dir, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "generate-reply-materials":
        result = prepare_reply_package(
            config,
            record_id=args.record_id,
            result_label=args.result_label,
            editor_name=args.editor_name,
            folder_date=args.folder_date,
            expected_issue=args.expected_issue,
            deadline_days=args.deadline_days,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "update-progress":
        result = update_progress(
            config,
            record_id=args.record_id,
            result_label=args.result_label,
            editor_name=args.editor_name,
            note_date=args.note_date,
            expected_issue=args.expected_issue,
        )
        print(result)
        return 0
    if args.command == "list-pending":
        state = StateStore(config.runtime.database)
        try:
            rows = state.list_pending()
            payload = [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "discipline": row["discipline"],
                    "status": row["status"],
                    "needs_manual_review": bool(row["needs_manual_review"]),
                    "needs_anonymization_check": bool(row["needs_anonymization_check"]),
                }
                for row in rows
            ]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        finally:
            state.close()
        return 0
    parser.error("未知命令")
    return 1
