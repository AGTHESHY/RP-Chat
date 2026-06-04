"""从完整 SP 文本文件恢复 prompts 表的 SFW/NSFW 拆分（用于数据修复）。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Prompt
from prompt_compose import NSFW_MARKER, split_prompt_content

SERVER_DIR = Path(__file__).resolve().parent
DEFAULT_PROMPT_DIR = SERVER_DIR / "seed_data" / "prompts"
_FILENAME_PATTERN = re.compile(
    r"^(segment_compress|history_merge)_(v\d+)_nsfw(_en)?\.txt$",
    re.IGNORECASE,
)


def import_prompt_file(
    db: Session,
    version: str,
    prompt_type: str,
    lang: str,
    full_content: str,
) -> bool:
    sfw, nsfw = split_prompt_content(full_content)
    row = (
        db.query(Prompt)
        .filter(
            Prompt.version == version,
            Prompt.prompt_type == prompt_type,
            Prompt.lang == lang,
        )
        .first()
    )
    if not row:
        row = Prompt(
            version=version,
            prompt_type=prompt_type,
            lang=lang,
            content_sfw=sfw,
            content_nsfw=nsfw,
        )
        db.add(row)
    else:
        row.content_sfw = sfw
        row.content_nsfw = nsfw
    return bool(nsfw.strip()) and NSFW_MARKER in sfw


def import_prompt_dir(db: Session, directory: Path) -> tuple[int, int]:
    if not directory.is_dir():
        return 0, 0

    updated = 0
    skipped = 0
    for path in sorted(directory.glob("*.txt")):
        match = _FILENAME_PATTERN.match(path.name)
        if not match:
            skipped += 1
            continue
        prompt_type = match.group(1).lower()
        version = match.group(2)
        lang = "en" if match.group(3) else "zh"

        full_content = path.read_text(encoding="utf-8")
        if import_prompt_file(db, version, prompt_type, lang, full_content):
            updated += 1
        else:
            skipped += 1

    db.commit()
    return updated, skipped


def needs_prompt_reseed(db: Session) -> bool:
    rows = db.execute(
        text(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN content_nsfw IS NULL OR content_nsfw = '' THEN 1 ELSE 0 END) AS empty_nsfw "
            "FROM prompts WHERE version IN ('v1', 'v2')"
        )
    ).mappings().first()
    if not rows or not rows["total"]:
        return True
    return int(rows["empty_nsfw"] or 0) == int(rows["total"])


def seed_prompts_from_dir(db: Session, directory: Path | None = None) -> int:
    directory = directory or DEFAULT_PROMPT_DIR
    if not directory.is_dir():
        return 0
    updated, _ = import_prompt_dir(db, directory)
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="从 .txt 完整 SP 恢复 MySQL prompts 表")
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_PROMPT_DIR,
        help="存放 segment_compress_v2_nsfw.txt 等文件的目录",
    )
    args = parser.parse_args()
    db = SessionLocal()
    try:
        updated, skipped = import_prompt_dir(db, args.dir)
        print(f"已更新 {updated} 个文件，跳过 {skipped} 个")
    finally:
        db.close()


if __name__ == "__main__":
    main()
