from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from models import RpTestRun
from rp_test_result_service import RpCompressSaveRequest, RpMergeSaveRequest, save_compress, save_merge

SERVER_DIR = Path(__file__).resolve().parent
RP_HISTORY_SEED_DIR = SERVER_DIR / "seed_data" / "rp_history"

MANDY_META_FILE = RP_HISTORY_SEED_DIR / "mandy_meta.json"
MANDY_COMPRESS_FILE = RP_HISTORY_SEED_DIR / "mandy_segment_compress.json"
MANDY_MERGE_FILE = RP_HISTORY_SEED_DIR / "mandy_history_merge.json"


def _has_run(db: Session, *, user_id: str, role_id: str, app_name: str, prompt_version: str) -> bool:
    return (
        db.query(RpTestRun)
        .filter(
            RpTestRun.user_id == user_id,
            RpTestRun.role_id == role_id,
            RpTestRun.app_name == app_name,
            RpTestRun.prompt_version == prompt_version,
        )
        .first()
        is not None
    )


def seed_mandy_rp_history(db: Session) -> int:
    """Import default Mandy compress + merge results into segment tables."""
    if not MANDY_META_FILE.is_file():
        return 0

    meta = json.loads(MANDY_META_FILE.read_text(encoding="utf-8"))
    user_id = meta["user_id"]
    role_id = meta["role_id"]
    app_name = meta["app_name"]
    model = (meta.get("model") or "").strip() or "seed-import"
    prompt_version = (meta.get("prompt_version") or "").strip()

    if _has_run(
        db,
        user_id=user_id,
        role_id=role_id,
        app_name=app_name,
        prompt_version=prompt_version,
    ):
        return 0

    inserted = 0
    if MANDY_COMPRESS_FILE.is_file():
        expected_result = json.loads(MANDY_COMPRESS_FILE.read_text(encoding="utf-8"))
        save_compress(
            db,
            RpCompressSaveRequest(
                user_id=user_id,
                role_id=role_id,
                app_name=app_name,
                role_name=meta["role_name"],
                prompt_version=prompt_version,
                segment_index=1,
                expected_result=expected_result,
                model=model,
            ),
        )
        inserted += 1

    if MANDY_MERGE_FILE.is_file():
        expected_result = json.loads(MANDY_MERGE_FILE.read_text(encoding="utf-8"))
        save_merge(
            db,
            RpMergeSaveRequest(
                user_id=user_id,
                role_id=role_id,
                app_name=app_name,
                role_name=meta["role_name"],
                prompt_version=prompt_version,
                merge_segment_start=1,
                merge_segment_end=1,
                expected_result=expected_result,
                model=model,
            ),
        )
        inserted += 1

    return inserted
