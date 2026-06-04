from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import RpEvalResult


class RpEvalSaveRequest(BaseModel):
    user_id: str
    role_id: str
    app_name: str = ""
    role_name: str = ""
    round_start: int = Field(default=1, ge=1)
    round_end: int = Field(default=10, ge=1)
    has_compress: bool = False
    has_merge: bool = False
    eval_system_prompt: str
    eval_result: dict[str, Any]
    raw_model_output: str = ""
    model: str = ""
    top_k: Optional[int] = None
    temperature: float = 0.0


def _extract_overall(eval_result: dict[str, Any]) -> tuple[int, float]:
    score_raw = eval_result.get("overall_score", 0)
    conf_raw = eval_result.get("overall_confidence", 0.0)
    try:
        score = int(score_raw)
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    try:
        conf = float(conf_raw)
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    return score, conf


def _row_to_summary(row: RpEvalResult) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "role_id": row.role_id,
        "app_name": row.app_name,
        "role_name": row.role_name,
        "round_start": row.round_start,
        "round_end": row.round_end,
        "has_compress": row.has_compress,
        "has_merge": row.has_merge,
        "model": row.model or "",
        "overall_score": row.overall_score,
        "overall_confidence": row.overall_confidence,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _row_to_detail(row: RpEvalResult) -> dict[str, Any]:
    return {
        **_row_to_summary(row),
        "eval_system_prompt": row.eval_system_prompt,
        "eval_result": json.loads(row.eval_result),
        "raw_model_output": row.raw_model_output,
        "top_k": row.top_k,
        "temperature": row.temperature,
    }


def create_rp_eval(db: Session, body: RpEvalSaveRequest) -> dict[str, Any]:
    if not body.eval_result:
        raise HTTPException(status_code=400, detail="eval_result is required")
    overall_score, overall_confidence = _extract_overall(body.eval_result)
    row = RpEvalResult(
        user_id=body.user_id.strip(),
        role_id=body.role_id.strip(),
        app_name=body.app_name.strip(),
        role_name=body.role_name.strip(),
        round_start=body.round_start,
        round_end=body.round_end,
        has_compress=body.has_compress,
        has_merge=body.has_merge,
        eval_system_prompt=body.eval_system_prompt,
        eval_result=json.dumps(body.eval_result, ensure_ascii=False),
        raw_model_output=body.raw_model_output or "",
        model=body.model or "",
        top_k=body.top_k,
        temperature=body.temperature,
        overall_score=overall_score,
        overall_confidence=overall_confidence,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_detail(row)


def list_rp_evaluations(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str = "",
) -> list[dict[str, Any]]:
    rows = (
        db.query(RpEvalResult)
        .filter(
            RpEvalResult.user_id == user_id.strip(),
            RpEvalResult.role_id == role_id.strip(),
            RpEvalResult.app_name == app_name.strip(),
        )
        .order_by(RpEvalResult.created_at.desc(), RpEvalResult.id.desc())
        .all()
    )
    return [_row_to_summary(row) for row in rows]


def get_rp_eval(db: Session, record_id: int) -> dict[str, Any]:
    row = db.query(RpEvalResult).filter(RpEvalResult.id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="RP evaluation not found")
    return _row_to_detail(row)
