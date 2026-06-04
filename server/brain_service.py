from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import BrainAnalysisResult

VALID_OVERALL = frozenset({"minor", "major", "hold"})


class BrainSaveRequest(BaseModel):
    rp_eval_id: int = Field(ge=1)
    user_id: str
    role_id: str
    app_name: str = ""
    role_name: str = ""
    round_start: int = Field(default=1, ge=1)
    round_end: int = Field(default=10, ge=1)
    compress_prompt_version: str = ""
    merge_prompt_version: str = ""
    brain_system_prompt: str = ""
    brain_result: dict[str, Any]
    raw_model_output: str = ""
    model: str = ""
    top_k: Optional[int] = None
    temperature: float = 0.0


def _normalize_overall(raw: str) -> str:
    value = (raw or "hold").strip()
    return value if value in VALID_OVERALL else "hold"


def _row_to_summary(row: BrainAnalysisResult) -> dict[str, Any]:
    return {
        "id": row.id,
        "rp_eval_id": row.rp_eval_id,
        "user_id": row.user_id,
        "role_id": row.role_id,
        "app_name": row.app_name,
        "role_name": row.role_name,
        "round_start": row.round_start,
        "round_end": row.round_end,
        "compress_prompt_version": row.compress_prompt_version or "",
        "merge_prompt_version": row.merge_prompt_version or "",
        "overall": row.overall or "hold",
        "model": row.model or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _row_to_detail(row: BrainAnalysisResult) -> dict[str, Any]:
    return {
        **_row_to_summary(row),
        "brain_system_prompt": row.brain_system_prompt,
        "brain_result": json.loads(row.brain_result),
        "raw_model_output": row.raw_model_output,
        "top_k": row.top_k,
        "temperature": row.temperature,
    }


def create_brain_analysis(db: Session, body: BrainSaveRequest) -> dict[str, Any]:
    if not body.brain_result:
        raise HTTPException(status_code=400, detail="brain_result is required")
    overall = _normalize_overall(str(body.brain_result.get("overall", "hold")))
    row = BrainAnalysisResult(
        rp_eval_id=body.rp_eval_id,
        user_id=body.user_id.strip(),
        role_id=body.role_id.strip(),
        app_name=body.app_name.strip(),
        role_name=body.role_name.strip(),
        round_start=body.round_start,
        round_end=body.round_end,
        compress_prompt_version=(body.compress_prompt_version or "").strip(),
        merge_prompt_version=(body.merge_prompt_version or "").strip(),
        overall=overall,
        brain_system_prompt=body.brain_system_prompt,
        brain_result=json.dumps(body.brain_result, ensure_ascii=False),
        raw_model_output=body.raw_model_output or "",
        model=body.model or "",
        top_k=body.top_k,
        temperature=body.temperature,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_detail(row)


def list_brain_analyses(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str = "",
) -> list[dict[str, Any]]:
    rows = (
        db.query(BrainAnalysisResult)
        .filter(
            BrainAnalysisResult.user_id == user_id.strip(),
            BrainAnalysisResult.role_id == role_id.strip(),
            BrainAnalysisResult.app_name == app_name.strip(),
        )
        .order_by(BrainAnalysisResult.created_at.desc(), BrainAnalysisResult.id.desc())
        .all()
    )
    return [_row_to_summary(row) for row in rows]


def get_brain_analysis(db: Session, record_id: int) -> dict[str, Any]:
    row = db.query(BrainAnalysisResult).filter(BrainAnalysisResult.id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Brain analysis not found")
    return _row_to_detail(row)


def delete_brain_analysis(db: Session, record_id: int) -> dict[str, Any]:
    row = db.query(BrainAnalysisResult).filter(BrainAnalysisResult.id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Brain analysis not found")
    data = _row_to_detail(row)
    db.delete(row)
    db.commit()
    return {"ok": True, "deleted": data}
