from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from redis_client import (
    delete_brain_record,
    get_brain_record,
    list_brain_record_ids,
    next_brain_record_id,
    save_brain_record,
    utc_now_iso,
)

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
    eval_mode: str = "single"
    evaluated_models: list[str] = Field(default_factory=list)


def _normalize_overall(raw: str) -> str:
    value = (raw or "hold").strip()
    return value if value in VALID_OVERALL else "hold"


def _to_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "rp_eval_id": record["rp_eval_id"],
        "user_id": record["user_id"],
        "role_id": record["role_id"],
        "app_name": record.get("app_name", ""),
        "role_name": record.get("role_name", ""),
        "round_start": record["round_start"],
        "round_end": record["round_end"],
        "compress_prompt_version": record.get("compress_prompt_version", ""),
        "merge_prompt_version": record.get("merge_prompt_version", ""),
        "overall": record.get("overall", "hold"),
        "model": record.get("model", ""),
        "eval_mode": record.get("eval_mode", "single"),
        "evaluated_models": record.get("evaluated_models", []),
        "created_at": record.get("created_at"),
    }


def _to_detail(record: dict[str, Any]) -> dict[str, Any]:
    return {
        **_to_summary(record),
        "brain_system_prompt": record.get("brain_system_prompt", ""),
        "brain_result": record.get("brain_result", {}),
        "raw_model_output": record.get("raw_model_output", ""),
        "top_k": record.get("top_k"),
        "temperature": record.get("temperature", 0.0),
    }


def create_brain_analysis(body: BrainSaveRequest) -> dict[str, Any]:
    if not body.brain_result:
        raise HTTPException(status_code=400, detail="brain_result is required")
    overall = _normalize_overall(str(body.brain_result.get("overall", "hold")))
    record: dict[str, Any] = {
        "id": next_brain_record_id(),
        "rp_eval_id": body.rp_eval_id,
        "user_id": body.user_id.strip(),
        "role_id": body.role_id.strip(),
        "app_name": body.app_name.strip(),
        "role_name": body.role_name.strip(),
        "round_start": body.round_start,
        "round_end": body.round_end,
        "compress_prompt_version": (body.compress_prompt_version or "").strip(),
        "merge_prompt_version": (body.merge_prompt_version or "").strip(),
        "overall": overall,
        "brain_system_prompt": body.brain_system_prompt,
        "brain_result": body.brain_result,
        "raw_model_output": body.raw_model_output or "",
        "model": body.model or "",
        "top_k": body.top_k,
        "temperature": body.temperature,
        "eval_mode": (body.eval_mode or "single").strip() or "single",
        "evaluated_models": body.evaluated_models or [],
        "created_at": utc_now_iso(),
        "_created_ts": time.time(),
    }
    save_brain_record(record)
    return _to_detail(record)


def list_brain_analyses(
    *,
    user_id: str,
    role_id: str,
    app_name: str = "",
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for record_id in list_brain_record_ids(user_id, role_id, app_name):
        record = get_brain_record(record_id)
        if not record:
            continue
        summaries.append(_to_summary(record))
    return summaries


def get_brain_analysis(record_id: int) -> dict[str, Any]:
    record = get_brain_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Brain analysis not found")
    return _to_detail(record)


def delete_brain_analysis(record_id: int) -> dict[str, Any]:
    record = delete_brain_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Brain analysis not found")
    return {"ok": True, "deleted": _to_detail(record)}
