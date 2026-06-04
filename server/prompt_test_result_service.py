from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
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
    """重跑：归属到该请求（run_group_id）"""
    run_group_id: Optional[int] = Field(default=None, ge=1)


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
        "run_group_id": row.run_group_id,
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


def _conversation_key(user_id: str, role_id: str, app_name: str) -> str:
    return f"{user_id}|{role_id}|{app_name}"


def _history_key(user_id: str, role_id: str, app_name: str, run_group_id: int) -> str:
    return f"{_conversation_key(user_id, role_id, app_name)}#{run_group_id}"


def _conversation_filter(
    user_id: str,
    role_id: str,
    app_name: str,
):
    return (
        PromptTestResult.user_id == user_id.strip(),
        PromptTestResult.role_id == role_id.strip(),
        PromptTestResult.app_name == app_name.strip(),
    )


def _next_run_group_id(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str,
) -> int:
    current = (
        db.query(func.max(PromptTestResult.run_group_id))
        .filter(*_conversation_filter(user_id, role_id, app_name))
        .scalar()
    )
    return int(current or 0) + 1


def _resolve_save_run_group_id(
    db: Session,
    body: PromptTestResultSaveRequest,
) -> int:
    if body.run_group_id is not None:
        exists = (
            db.query(PromptTestResult.id)
            .filter(
                *_conversation_filter(body.user_id, body.role_id, body.app_name),
                PromptTestResult.run_group_id == body.run_group_id,
            )
            .first()
        )
        if not exists:
            raise HTTPException(status_code=404, detail="run_group_id not found for conversation")
        return body.run_group_id

    # 仅在前端显式传入 run_group_id（同批并行 / 历史重跑）时并入原请求；
    # 不再按「轮次 + SP 版本」自动并入旧记录，避免多次测试堆在同一组导致模型数虚高。
    return _next_run_group_id(
        db,
        user_id=body.user_id,
        role_id=body.role_id,
        app_name=body.app_name,
    )


def _apply_body_to_row(row: PromptTestResult, body: PromptTestResultSaveRequest, payload: str) -> None:
    row.role_name = body.role_name
    row.expected_result = payload
    row.round_start = body.round_start
    row.round_end = body.round_end
    row.prompt_version = body.prompt_version
    row.model = body.model.strip()
    row.top_k = body.top_k
    row.temperature = body.temperature


def _build_model_runs(rows: list[PromptTestResult]) -> list[dict[str, Any]]:
    by_model: dict[str, dict[str, Any]] = {}
    for row in rows:
        model = row.model or ""
        if model not in by_model:
            by_model[model] = {
                "model": model,
                "compress_record_id": None,
                "merge_record_id": None,
                "compress": None,
                "merge": None,
                "compress_run": None,
                "merge_run": None,
                "latest_updated_at": None,
            }
        slot = by_model[model]
        ts = row.updated_at.isoformat() if row.updated_at else None
        if row.prompt_type == "segment_compress":
            slot["compress_record_id"] = row.id
            slot["compress"] = json.loads(row.expected_result)
            slot["compress_run"] = _run_meta(row)
        elif row.prompt_type == "history_merge":
            slot["merge_record_id"] = row.id
            slot["merge"] = json.loads(row.expected_result)
            slot["merge_run"] = _run_meta(row)
        if ts and (not slot["latest_updated_at"] or ts > slot["latest_updated_at"]):
            slot["latest_updated_at"] = ts

    runs = sorted(
        by_model.values(),
        key=lambda item: item["latest_updated_at"] or "",
        reverse=True,
    )
    return [
        item
        for item in runs
        if (item["model"] or "").strip()
        and (item["compress"] is not None or item["merge"] is not None)
    ]


def _pick_model_run(model_runs: list[dict[str, Any]], model: Optional[str]) -> dict[str, Any] | None:
    if not model_runs:
        return None
    if model:
        for item in model_runs:
            if item["model"] == model:
                return item
        return None
    return model_runs[0]


def regroup_prompt_test_run_groups(db: Session) -> None:
    """按请求维度合并 run_group_id，并去重 (run_group_id, model, prompt_type)。"""
    rows = db.query(PromptTestResult).order_by(PromptTestResult.id.asc()).all()
    if not rows:
        return

    buckets: dict[tuple[Any, ...], list[PromptTestResult]] = defaultdict(list)
    for row in rows:
        key = (
            row.user_id,
            row.role_id,
            row.app_name,
            row.round_start,
            row.round_end,
            row.prompt_version or "",
        )
        buckets[key].append(row)

    for group_rows in buckets.values():
        group_id = min(r.id for r in group_rows)
        for row in group_rows:
            row.run_group_id = group_id
    db.flush()

    grouped_rows: dict[tuple[int, str, str], list[PromptTestResult]] = defaultdict(list)
    for row in rows:
        grouped_rows[(row.run_group_id, row.model or "", row.prompt_type)].append(row)

    for dup_rows in grouped_rows.values():
        if len(dup_rows) <= 1:
            continue
        dup_rows.sort(
            key=lambda r: (r.updated_at or r.created_at, r.id),
            reverse=True,
        )
        for stale in dup_rows[1:]:
            db.delete(stale)
    db.commit()


def list_prompt_test_results(
    db: Session,
    *,
    user_id: Optional[str] = None,
    role_id: Optional[str] = None,
    role_name: Optional[str] = None,
    prompt_type: Optional[str] = None,
    run_group_id: Optional[int] = None,
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
    if run_group_id is not None:
        query = query.filter(PromptTestResult.run_group_id == run_group_id)

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
    model: Optional[str] = None,
    run_group_id: Optional[int] = None,
) -> dict[str, Any]:
    query = db.query(PromptTestResult).filter(
        *_conversation_filter(user_id, role_id, app_name),
        PromptTestResult.prompt_type == prompt_type,
    )
    if run_group_id is not None:
        query = query.filter(PromptTestResult.run_group_id == run_group_id)
    if model:
        query = query.filter(PromptTestResult.model == model.strip())
    row = query.order_by(PromptTestResult.updated_at.desc(), PromptTestResult.id.desc()).first()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt test result not found")
    return _row_to_dict(row)


def save_prompt_test_result(db: Session, body: PromptTestResultSaveRequest) -> dict[str, Any]:
    model = body.model.strip()
    if not model:
        raise HTTPException(status_code=400, detail="model is required")

    payload = json.dumps(body.expected_result, ensure_ascii=False)
    run_group_id = _resolve_save_run_group_id(db, body)

    existing = (
        db.query(PromptTestResult)
        .filter(
            *_conversation_filter(body.user_id, body.role_id, body.app_name),
            PromptTestResult.run_group_id == run_group_id,
            PromptTestResult.model == model,
            PromptTestResult.prompt_type == body.prompt_type,
        )
        .first()
    )

    if existing:
        _apply_body_to_row(existing, body, payload)
        row = existing
    else:
        row = PromptTestResult(
            user_id=body.user_id.strip(),
            role_id=body.role_id.strip(),
            app_name=body.app_name.strip(),
            role_name=body.role_name,
            run_group_id=run_group_id,
            prompt_type=body.prompt_type,
            expected_result=payload,
            round_start=body.round_start,
            round_end=body.round_end,
            prompt_version=body.prompt_version,
            model=model,
            top_k=body.top_k,
            temperature=body.temperature,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def _resolve_run_group_id(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str,
    run_group_id: Optional[int],
) -> int:
    if run_group_id is not None:
        exists = (
            db.query(PromptTestResult.id)
            .filter(
                *_conversation_filter(user_id, role_id, app_name),
                PromptTestResult.run_group_id == run_group_id,
            )
            .first()
        )
        if not exists:
            raise HTTPException(status_code=404, detail="RP history not found")
        return run_group_id

    rows = (
        db.query(PromptTestResult)
        .filter(*_conversation_filter(user_id, role_id, app_name))
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="RP history not found")
    latest_by_group: dict[int, Any] = {}
    for row in rows:
        ts = row.updated_at
        prev = latest_by_group.get(row.run_group_id)
        if prev is None or (ts and (prev is None or ts > prev)):
            latest_by_group[row.run_group_id] = ts
    return max(latest_by_group.keys(), key=lambda gid: latest_by_group[gid] or "")


def list_rp_history(
    db: Session,
    *,
    user_id: Optional[str] = None,
    role_id: Optional[str] = None,
    role_name: Optional[str] = None,
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

    rows = query.order_by(
        PromptTestResult.updated_at.desc(),
        PromptTestResult.id.desc(),
    ).all()

    grouped: dict[int, dict[str, Any]] = {}
    rows_per_group: dict[int, list[PromptTestResult]] = defaultdict(list)

    for row in rows:
        run_group_id = int(row.run_group_id or row.id)
        conv_key = _conversation_key(row.user_id, row.role_id, row.app_name)
        entry = grouped.setdefault(
            run_group_id,
            {
                "conversation_key": conv_key,
                "history_key": _history_key(row.user_id, row.role_id, row.app_name, run_group_id),
                "run_group_id": run_group_id,
                "user_id": row.user_id,
                "role_id": row.role_id,
                "app_name": row.app_name,
                "role_name": row.role_name,
                "prompt_version": row.prompt_version or "",
                "has_compress": False,
                "has_merge": False,
                "round_start": row.round_start,
                "round_end": row.round_end,
                "latest_updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "model_count": 0,
            },
        )
        entry["role_name"] = row.role_name
        if not entry["prompt_version"] and row.prompt_version:
            entry["prompt_version"] = row.prompt_version
        if row.prompt_type == "segment_compress":
            entry["has_compress"] = True
        elif row.prompt_type == "history_merge":
            entry["has_merge"] = True
        rows_per_group[run_group_id].append(row)
        ts = row.updated_at.isoformat() if row.updated_at else None
        if ts and (not entry["latest_updated_at"] or ts > entry["latest_updated_at"]):
            entry["latest_updated_at"] = ts

    for run_group_id, entry in grouped.items():
        display_runs = _build_model_runs(rows_per_group[run_group_id])
        entry["model_count"] = len(display_runs)
        if not display_runs:
            entry["has_compress"] = False
            entry["has_merge"] = False

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
    run_group_id: Optional[int] = None,
    model: Optional[str] = None,
) -> dict[str, Any]:
    resolved_group = _resolve_run_group_id(
        db,
        user_id=user_id,
        role_id=role_id,
        app_name=app_name,
        run_group_id=run_group_id,
    )
    rows = (
        db.query(PromptTestResult)
        .filter(
            *_conversation_filter(user_id, role_id, app_name),
            PromptTestResult.run_group_id == resolved_group,
        )
        .order_by(PromptTestResult.updated_at.desc(), PromptTestResult.id.desc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="RP history not found")

    model_runs = _build_model_runs(rows)
    picked = _pick_model_run(model_runs, model.strip() if model else None)
    anchor = rows[0]
    conv_key = _conversation_key(user_id, role_id, app_name)

    result: dict[str, Any] = {
        "conversation_key": conv_key,
        "history_key": _history_key(user_id, role_id, app_name, resolved_group),
        "run_group_id": resolved_group,
        "user_id": user_id,
        "role_id": role_id,
        "app_name": app_name,
        "role_name": anchor.role_name,
        "prompt_version": anchor.prompt_version or "",
        "round_start": anchor.round_start,
        "round_end": anchor.round_end,
        "model_runs": model_runs,
        "compress": picked["compress"] if picked else None,
        "merge": picked["merge"] if picked else None,
        "compress_record_id": picked["compress_record_id"] if picked else None,
        "merge_record_id": picked["merge_record_id"] if picked else None,
        "compress_updated_at": picked["compress_run"]["updated_at"] if picked and picked.get("compress_run") else None,
        "merge_updated_at": picked["merge_run"]["updated_at"] if picked and picked.get("merge_run") else None,
        "compress_run": picked["compress_run"] if picked else None,
        "merge_run": picked["merge_run"] if picked else None,
    }
    return result
