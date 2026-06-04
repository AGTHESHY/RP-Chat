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
    compress_prompt_version: str = ""
    merge_prompt_version: str = ""
    eval_system_prompt: str
    eval_result: dict[str, Any]
    raw_model_output: str = ""
    model: str = ""
    top_k: Optional[int] = None
    temperature: float = 0.0
    eval_mode: str = "single"
    evaluated_models: list[str] = Field(default_factory=list)


def _extract_overall(eval_result: dict[str, Any]) -> tuple[int, float]:
    mode = str(eval_result.get("eval_mode", "single"))
    model_scores = eval_result.get("model_scores")
    if mode == "multi_compare" and isinstance(model_scores, list) and model_scores:
        scores: list[int] = []
        confs: list[float] = []
        for item in model_scores:
            if not isinstance(item, dict):
                continue
            try:
                scores.append(max(0, min(100, int(item.get("overall_score", 0)))))
            except (TypeError, ValueError):
                scores.append(0)
            try:
                confs.append(max(0.0, min(1.0, float(item.get("overall_confidence", 0.0)))))
            except (TypeError, ValueError):
                confs.append(0.0)
        if scores:
            avg_score = round(sum(scores) / len(scores))
            avg_conf = sum(confs) / len(confs) if confs else 0.0
            return avg_score, avg_conf

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


def _normalize_eval_mode(body: RpEvalSaveRequest, eval_result: dict[str, Any]) -> str:
    mode = (body.eval_mode or str(eval_result.get("eval_mode", ""))).strip()
    if mode == "multi_compare":
        return "multi_compare"
    models = body.evaluated_models or []
    if len(models) > 1:
        return "multi_compare"
    if isinstance(eval_result.get("model_scores"), list) and len(eval_result["model_scores"]) > 1:
        return "multi_compare"
    return "single"


def _normalize_evaluated_models(body: RpEvalSaveRequest, eval_result: dict[str, Any]) -> list[str]:
    if body.evaluated_models:
        return [str(m).strip() for m in body.evaluated_models if str(m).strip()]
    model_scores = eval_result.get("model_scores")
    if isinstance(model_scores, list):
        names = []
        for item in model_scores:
            if isinstance(item, dict) and item.get("model"):
                names.append(str(item["model"]).strip())
        if names:
            return names
    return []


def _row_to_summary(row: RpEvalResult) -> dict[str, Any]:
    try:
        evaluated_models = json.loads(row.evaluated_models or "[]")
        if not isinstance(evaluated_models, list):
            evaluated_models = []
    except json.JSONDecodeError:
        evaluated_models = []
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
        "compress_prompt_version": row.compress_prompt_version or "",
        "merge_prompt_version": row.merge_prompt_version or "",
        "model": row.model or "",
        "eval_mode": getattr(row, "eval_mode", None) or "single",
        "evaluated_models": evaluated_models,
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
    eval_mode = _normalize_eval_mode(body, body.eval_result)
    evaluated_models = _normalize_evaluated_models(body, body.eval_result)
    row = RpEvalResult(
        user_id=body.user_id.strip(),
        role_id=body.role_id.strip(),
        app_name=body.app_name.strip(),
        role_name=body.role_name.strip(),
        round_start=body.round_start,
        round_end=body.round_end,
        has_compress=body.has_compress,
        has_merge=body.has_merge,
        compress_prompt_version=(body.compress_prompt_version or "").strip(),
        merge_prompt_version=(body.merge_prompt_version or "").strip(),
        eval_system_prompt=body.eval_system_prompt,
        eval_result=json.dumps(body.eval_result, ensure_ascii=False),
        raw_model_output=body.raw_model_output or "",
        model=body.model or "",
        top_k=body.top_k,
        temperature=body.temperature,
        overall_score=overall_score,
        overall_confidence=overall_confidence,
        eval_mode=eval_mode,
        evaluated_models=json.dumps(evaluated_models, ensure_ascii=False),
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


def delete_rp_eval(db: Session, record_id: int) -> dict[str, Any]:
    row = db.query(RpEvalResult).filter(RpEvalResult.id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="RP evaluation not found")
    data = _row_to_detail(row)
    db.delete(row)
    db.commit()
    return {"ok": True, "deleted": data}
