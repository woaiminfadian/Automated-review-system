from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Iterable


INVALID_FILENAME_CHARS = r'[\\/:*?"<>|]'


def sanitize_filename(value: str, fallback: str = "未命名") -> str:
    cleaned = re.sub(INVALID_FILENAME_CHARS, " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")
    return cleaned or fallback


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = path.with_name(f"{stem}({counter}){suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_docx_text_from_bytes(payload: bytes) -> str:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    text = re.sub(r"<[^>]+>", "\n", xml)
    return normalize_whitespace(text)


def extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    text = re.sub(r"<[^>]+>", "\n", xml)
    return normalize_whitespace(text)


def chunked_lines(text: str) -> Iterable[str]:
    for line in normalize_whitespace(text).split("\n"):
        line = line.strip()
        if line:
            yield line
