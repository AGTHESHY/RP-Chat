"""Server-side helpers for jailbreak modules_json validation (compose runs on frontend)."""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import HTTPException

VALID_CONTENT_MODES = frozenset({"plain", "variable"})


def validate_content_mode(mode: str) -> str:
    value = (mode or "plain").strip()
    if value not in VALID_CONTENT_MODES:
        raise HTTPException(status_code=400, detail="content_mode must be plain or variable")
    return value


def normalize_modules_json(raw: Optional[dict[str, Any]]) -> Optional[str]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="modules_json must be an object")
    base = raw.get("baseSections")
    variables = raw.get("variables")
    if not isinstance(base, list) or not isinstance(variables, list):
        raise HTTPException(
            status_code=400,
            detail="modules_json must contain baseSections and variables arrays",
        )
    return json.dumps(raw, ensure_ascii=False)


def parse_modules_json(stored: Optional[str]) -> Optional[dict[str, Any]]:
    if not stored:
        return None
    try:
        return json.loads(stored)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid modules_json: {exc}") from exc
