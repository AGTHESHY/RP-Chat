from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import PromptTestResult


class PromptTestResultSaveRequest(BaseModel):
    user_id: str
    role_id: str
    app_name: str = ""
    role_name: str = ""
    prompt_type: str
    expected_result: dict[str, Any]
    round_start: int = Field(default=1, ge=1)
    round_end: int = Field(default=10, ge=1)
    prompt_version: str = ""
    model: str = ""
    top_k: Optional[int] = None
    temperature: float = 0.0


def _run_meta(row: PromptTestResult) -> dict[str, Any]:
    return {
        "prompt_version": row.prompt_version or "",
        "model": row.model or "",
        "top_k": row.top_k,
        "temperature": row.temperature,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _row_to_dict(row: PromptTestResult) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "role_id": row.role_id,
        "app_name": row.app_name,
        "role_name": row.role_name,
        "prompt_type": row.prompt_type,
        "expected_result": json.loads(row.expected_result),
        "round_start": row.round_start,
        "round_end": row.round_end,
        "prompt_version": row.prompt_version or "",
        "model": row.model or "",
        "top_k": row.top_k,
        "temperature": row.temperature,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_prompt_test_results(
    db: Session,
    *,
    user_id: Optional[str] = None,
    role_id: Optional[str] = None,
    role_name: Optional[str] = None,
    prompt_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    query = db.query(PromptTestResult)
    if user_id:
        keyword = user_id.strip()
        if keyword:
            query = query.filter(PromptTestResult.user_id.contains(keyword))
    if role_id:
        keyword = role_id.strip()
        if keyword:
            query = query.filter(PromptTestResult.role_id.contains(keyword))
    if role_name:
        keyword = role_name.strip()
        if keyword:
            query = query.filter(PromptTestResult.role_name.contains(keyword))
    if prompt_type:
        keyword = prompt_type.strip()
        if keyword:
            query = query.filter(PromptTestResult.prompt_type == keyword)

    rows = query.order_by(
        PromptTestResult.updated_at.desc(),
        PromptTestResult.id.desc(),
    ).all()
    return [_row_to_dict(row) for row in rows]


def get_prompt_test_result(db: Session, record_id: int) -> dict[str, Any]:
    row = db.query(PromptTestResult).filter(PromptTestResult.id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt test result not found")
    return _row_to_dict(row)


def get_prompt_test_result_for_conversation(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str,
    prompt_type: str,
) -> dict[str, Any]:
    row = (
        db.query(PromptTestResult)
        .filter(
            PromptTestResult.user_id == user_id,
            PromptTestResult.role_id == role_id,
            PromptTestResult.app_name == app_name,
            PromptTestResult.prompt_type == prompt_type,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Prompt test result not found")
    return _row_to_dict(row)


def save_prompt_test_result(db: Session, body: PromptTestResultSaveRequest) -> dict[str, Any]:
    existing = (
        db.query(PromptTestResult)
        .filter(
            PromptTestResult.user_id == body.user_id,
            PromptTestResult.role_id == body.role_id,
            PromptTestResult.app_name == body.app_name,
            PromptTestResult.prompt_type == body.prompt_type,
        )
        .first()
    )
    payload = json.dumps(body.expected_result, ensure_ascii=False)
    if existing:
        existing.role_name = body.role_name
        existing.expected_result = payload
        existing.round_start = body.round_start
        existing.round_end = body.round_end
        existing.prompt_version = body.prompt_version
        existing.model = body.model
        existing.top_k = body.top_k
        existing.temperature = body.temperature
        row = existing
    else:
        row = PromptTestResult(
            user_id=body.user_id,
            role_id=body.role_id,
            app_name=body.app_name,
            role_name=body.role_name,
            prompt_type=body.prompt_type,
            expected_result=payload,
            round_start=body.round_start,
            round_end=body.round_end,
            prompt_version=body.prompt_version,
            model=body.model,
            top_k=body.top_k,
            temperature=body.temperature,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def _conversation_key(user_id: str, role_id: str, app_name: str) -> str:
    return f"{user_id}|{role_id}|{app_name}"


def list_rp_history(
    db: Session,
    *,
    user_id: Optional[str] = None,
    role_id: Optional[str] = None,
    role_name: Optional[str] = None,
) -> list[dict[str, Any]]:
    rows = list_prompt_test_results(
        db,
        user_id=user_id,
        role_id=role_id,
        role_name=role_name,
    )
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["user_id"], row["role_id"], row["app_name"])
        entry = grouped.setdefault(
            key,
            {
                "conversation_key": _conversation_key(*key),
                "user_id": row["user_id"],
                "role_id": row["role_id"],
                "app_name": row["app_name"],
                "role_name": row["role_name"],
                "has_compress": False,
                "has_merge": False,
                "round_start": row["round_start"],
                "round_end": row["round_end"],
                "latest_updated_at": row["updated_at"],
            },
        )
        entry["role_name"] = row["role_name"]
        if row["prompt_type"] == "segment_compress":
            entry["has_compress"] = True
        elif row["prompt_type"] == "history_merge":
            entry["has_merge"] = True
        entry["round_start"] = min(entry["round_start"], row["round_start"])
        entry["round_end"] = max(entry["round_end"], row["round_end"])
        if row["updated_at"] and (
            not entry["latest_updated_at"] or row["updated_at"] > entry["latest_updated_at"]
        ):
            entry["latest_updated_at"] = row["updated_at"]

    return sorted(
        grouped.values(),
        key=lambda item: item["latest_updated_at"] or "",
        reverse=True,
    )


def get_rp_history_detail(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str,
) -> dict[str, Any]:
    compress_row = (
        db.query(PromptTestResult)
        .filter(
            PromptTestResult.user_id == user_id,
            PromptTestResult.role_id == role_id,
            PromptTestResult.app_name == app_name,
            PromptTestResult.prompt_type == "segment_compress",
        )
        .first()
    )
    merge_row = (
        db.query(PromptTestResult)
        .filter(
            PromptTestResult.user_id == user_id,
            PromptTestResult.role_id == role_id,
            PromptTestResult.app_name == app_name,
            PromptTestResult.prompt_type == "history_merge",
        )
        .first()
    )
    if not compress_row and not merge_row:
        raise HTTPException(status_code=404, detail="RP history not found")

    role_name = ""
    round_start = 1
    round_end = 10
    if compress_row:
        role_name = compress_row.role_name
        round_start = compress_row.round_start
        round_end = compress_row.round_end
    elif merge_row:
        role_name = merge_row.role_name
        round_start = merge_row.round_start
        round_end = merge_row.round_end

    return {
        "conversation_key": _conversation_key(user_id, role_id, app_name),
        "user_id": user_id,
        "role_id": role_id,
        "app_name": app_name,
        "role_name": role_name,
        "round_start": round_start,
        "round_end": round_end,
        "compress": json.loads(compress_row.expected_result) if compress_row else None,
        "merge": json.loads(merge_row.expected_result) if merge_row else None,
        "compress_updated_at": compress_row.updated_at.isoformat() if compress_row and compress_row.updated_at else None,
        "merge_updated_at": merge_row.updated_at.isoformat() if merge_row and merge_row.updated_at else None,
        "compress_run": _run_meta(compress_row) if compress_row else None,
        "merge_run": _run_meta(merge_row) if merge_row else None,
    }
