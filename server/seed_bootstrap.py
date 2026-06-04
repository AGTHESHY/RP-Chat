from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from chat_qa_import import ensure_chat_qa_cases
from prompt_seed import needs_prompt_reseed, seed_prompts_from_dir
from rp_history_seed import seed_mandy_rp_history

SERVER_DIR = Path(__file__).resolve().parent
SEED_DIR = SERVER_DIR / "seed_data"
CHAT_QA_SEED_DIR = SEED_DIR / "chat_qa"


def bootstrap_seed_data(db: Session) -> None:
    """Import bundled seed files when tables are empty (fresh install)."""
    ensure_chat_qa_cases(db, CHAT_QA_SEED_DIR)
    seed_mandy_rp_history(db)
    if needs_prompt_reseed(db):
        seed_prompts_from_dir(db, SEED_DIR / "prompts")
