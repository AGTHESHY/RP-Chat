from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from models import PromptTestResult
from prompt_test_result_service import PromptTestResultSaveRequest, save_prompt_test_result

SERVER_DIR = Path(__file__).resolve().parent
RP_HISTORY_SEED_DIR = SERVER_DIR / "seed_data" / "rp_history"

MANDY_META_FILE = RP_HISTORY_SEED_DIR / "mandy_meta.json"
MANDY_COMPRESS_FILE = RP_HISTORY_SEED_DIR / "mandy_segment_compress.json"
MANDY_MERGE_FILE = RP_HISTORY_SEED_DIR / "mandy_history_merge.json"


def _has_result(db: Session, *, user_id: str, role_id: str, app_name: str, prompt_type: str) -> bool:
    return (
        db.query(PromptTestResult)
        .filter(
            PromptTestResult.user_id == user_id,
            PromptTestResult.role_id == role_id,
            PromptTestResult.app_name == app_name,
            PromptTestResult.prompt_type == prompt_type,
        )
        .first()
        is not None
    )


def seed_mandy_rp_history(db: Session) -> int:
    """Import default Mandy compress + merge results into prompt_test_results."""
    if not MANDY_META_FILE.is_file():
        return 0

    meta = json.loads(MANDY_META_FILE.read_text(encoding="utf-8"))
    user_id = meta["user_id"]
    role_id = meta["role_id"]
    app_name = meta["app_name"]
    inserted = 0

    seeds: list[tuple[str, Path]] = [
        ("segment_compress", MANDY_COMPRESS_FILE),
        ("history_merge", MANDY_MERGE_FILE),
    ]
    for prompt_type, path in seeds:
        if _has_result(db, user_id=user_id, role_id=role_id, app_name=app_name, prompt_type=prompt_type):
            continue
        if not path.is_file():
            continue
        expected_result = json.loads(path.read_text(encoding="utf-8"))
        save_prompt_test_result(
            db,
            PromptTestResultSaveRequest(
                user_id=user_id,
                role_id=role_id,
                app_name=app_name,
                role_name=meta["role_name"],
                prompt_type=prompt_type,
                expected_result=expected_result,
                round_start=meta.get("round_start", 1),
                round_end=meta.get("round_end", 10),
            ),
        )
        inserted += 1

    return inserted
