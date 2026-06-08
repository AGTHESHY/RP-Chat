from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import RpCompressResult, RpMergeResult, RpTestRun


def segment_range_for_index(segment_index: int) -> tuple[int, int]:
    if segment_index < 1:
        raise ValueError("segment_index must be >= 1")
    if segment_index == 1:
        return 1, 10
    start = 10 * (segment_index - 1) + 1
    end = 10 * segment_index + 1
    return start, end


class RpCompressSaveRequest(BaseModel):
    user_id: str
    role_id: str
    app_name: str = ""
    role_name: str = ""
    prompt_version: str = ""
    segment_index: int = Field(ge=1)
    expected_result: dict[str, Any]
    model: str = ""
    top_k: Optional[int] = None
    temperature: float = 0.0
    run_id: Optional[int] = Field(default=None, ge=1)


class RpMergeSaveRequest(BaseModel):
    user_id: str
    role_id: str
    app_name: str = ""
    role_name: str = ""
    prompt_version: str = ""
    merge_segment_start: int = Field(ge=1)
    merge_segment_end: int = Field(ge=1)
    expected_result: dict[str, Any]
    model: str = ""
    top_k: Optional[int] = None
    temperature: float = 0.0
    run_id: Optional[int] = Field(default=None, ge=1)


def _conversation_key(user_id: str, role_id: str, app_name: str) -> str:
    return f"{user_id}|{role_id}|{app_name}"


def _history_key(user_id: str, role_id: str, app_name: str, run_id: int) -> str:
    return f"{_conversation_key(user_id, role_id, app_name)}#{run_id}"


def _conversation_filter(user_id: str, role_id: str, app_name: str):
    return (
        RpTestRun.user_id == user_id.strip(),
        RpTestRun.role_id == role_id.strip(),
        RpTestRun.app_name == app_name.strip(),
    )


def _compress_conv_filter(user_id: str, role_id: str, app_name: str):
    return (
        RpCompressResult.user_id == user_id.strip(),
        RpCompressResult.role_id == role_id.strip(),
        RpCompressResult.app_name == app_name.strip(),
    )


def _run_meta(
    *,
    prompt_version: str,
    model: str,
    top_k: Optional[int],
    temperature: float,
    updated_at,
) -> dict[str, Any]:
    return {
        "prompt_version": prompt_version or "",
        "model": model or "",
        "top_k": top_k,
        "temperature": temperature,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def _compress_to_dict(row: RpCompressResult) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "run_group_id": row.run_id,
        "user_id": row.user_id,
        "role_id": row.role_id,
        "app_name": row.app_name,
        "prompt_version": row.prompt_version or "",
        "segment_index": row.segment_index,
        "round_start": row.round_start,
        "round_end": row.round_end,
        "model": row.model or "",
        "expected_result": json.loads(row.expected_result),
        "top_k": row.top_k,
        "temperature": row.temperature,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _merge_to_dict(row: RpMergeResult) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "run_group_id": row.run_id,
        "user_id": row.user_id,
        "role_id": row.role_id,
        "app_name": row.app_name,
        "prompt_version": row.prompt_version or "",
        "merge_segment_start": row.merge_segment_start,
        "merge_segment_end": row.merge_segment_end,
        "round_start": row.round_start,
        "round_end": row.round_end,
        "model": row.model or "",
        "expected_result": json.loads(row.expected_result),
        "top_k": row.top_k,
        "temperature": row.temperature,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _run_to_dict(row: RpTestRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.id,
        "run_group_id": row.id,
        "user_id": row.user_id,
        "role_id": row.role_id,
        "app_name": row.app_name,
        "role_name": row.role_name,
        "prompt_version": row.prompt_version or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def resolve_or_create_run(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str,
    role_name: str,
    prompt_version: str,
    run_id: Optional[int] = None,
) -> RpTestRun:
    if run_id is not None:
        row = (
            db.query(RpTestRun)
            .filter(
                RpTestRun.id == run_id,
                *_conversation_filter(user_id, role_id, app_name),
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="run_id not found for conversation")
        if role_name:
            row.role_name = role_name
        return row

    existing = (
        db.query(RpTestRun)
        .filter(
            *_conversation_filter(user_id, role_id, app_name),
            RpTestRun.prompt_version == prompt_version.strip(),
        )
        .first()
    )
    if existing:
        if role_name:
            existing.role_name = role_name
        return existing

    row = RpTestRun(
        user_id=user_id.strip(),
        role_id=role_id.strip(),
        app_name=app_name.strip(),
        role_name=role_name,
        prompt_version=prompt_version.strip(),
    )
    db.add(row)
    db.flush()
    return row


def _validate_new_segment_index(
    db: Session,
    *,
    run_id: int,
    model: str,
    segment_index: int,
) -> None:
    rows = (
        db.query(RpCompressResult.segment_index)
        .filter(RpCompressResult.run_id == run_id, RpCompressResult.model == model)
        .order_by(RpCompressResult.segment_index.asc())
        .all()
    )
    existing = [int(r[0]) for r in rows]
    if segment_index in existing:
        return
    if not existing:
        if segment_index != 1:
            raise HTTPException(status_code=400, detail="首段须为 segment_index=1")
        return
    max_index = max(existing)
    if segment_index != max_index + 1:
        raise HTTPException(
            status_code=400,
            detail=f"新段须连续追加，当前最大段为 {max_index}，只能保存段 {max_index + 1}",
        )


def save_compress(db: Session, body: RpCompressSaveRequest) -> dict[str, Any]:
    model = body.model.strip()
    if not model:
        raise HTTPException(status_code=400, detail="model is required")

    expected_start, expected_end = segment_range_for_index(body.segment_index)
    run = resolve_or_create_run(
        db,
        user_id=body.user_id,
        role_id=body.role_id,
        app_name=body.app_name,
        role_name=body.role_name,
        prompt_version=body.prompt_version,
        run_id=body.run_id,
    )
    _validate_new_segment_index(
        db,
        run_id=run.id,
        model=model,
        segment_index=body.segment_index,
    )

    payload = json.dumps(body.expected_result, ensure_ascii=False)
    existing = (
        db.query(RpCompressResult)
        .filter(
            *_compress_conv_filter(body.user_id, body.role_id, body.app_name),
            RpCompressResult.prompt_version == body.prompt_version.strip(),
            RpCompressResult.model == model,
            RpCompressResult.segment_index == body.segment_index,
        )
        .first()
    )

    if existing:
        existing.run_id = run.id
        existing.expected_result = payload
        existing.round_start = expected_start
        existing.round_end = expected_end
        existing.top_k = body.top_k
        existing.temperature = body.temperature
        row = existing
    else:
        row = RpCompressResult(
            run_id=run.id,
            user_id=body.user_id.strip(),
            role_id=body.role_id.strip(),
            app_name=body.app_name.strip(),
            prompt_version=body.prompt_version.strip(),
            segment_index=body.segment_index,
            round_start=expected_start,
            round_end=expected_end,
            model=model,
            expected_result=payload,
            top_k=body.top_k,
            temperature=body.temperature,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    result = _compress_to_dict(row)
    result["run_group_id"] = run.id
    return result


def save_merge(db: Session, body: RpMergeSaveRequest) -> dict[str, Any]:
    model = body.model.strip()
    if not model:
        raise HTTPException(status_code=400, detail="model is required")
    if body.merge_segment_start > body.merge_segment_end:
        raise HTTPException(status_code=400, detail="merge_segment_start cannot exceed merge_segment_end")

    run = resolve_or_create_run(
        db,
        user_id=body.user_id,
        role_id=body.role_id,
        app_name=body.app_name,
        role_name=body.role_name,
        prompt_version=body.prompt_version,
        run_id=body.run_id,
    )

    compress_rows = (
        db.query(RpCompressResult)
        .filter(
            RpCompressResult.run_id == run.id,
            RpCompressResult.model == model,
            RpCompressResult.segment_index >= body.merge_segment_start,
            RpCompressResult.segment_index <= body.merge_segment_end,
        )
        .order_by(RpCompressResult.segment_index.asc())
        .all()
    )
    needed = body.merge_segment_end - body.merge_segment_start + 1
    if len(compress_rows) < needed:
        raise HTTPException(
            status_code=400,
            detail=f"段 {body.merge_segment_start}-{body.merge_segment_end} 的 compress 尚未全部完成",
        )

    round_start = min(row.round_start for row in compress_rows)
    round_end = max(row.round_end for row in compress_rows)
    payload = json.dumps(body.expected_result, ensure_ascii=False)

    existing = (
        db.query(RpMergeResult)
        .filter(
            RpMergeResult.user_id == body.user_id.strip(),
            RpMergeResult.role_id == body.role_id.strip(),
            RpMergeResult.app_name == body.app_name.strip(),
            RpMergeResult.prompt_version == body.prompt_version.strip(),
            RpMergeResult.model == model,
            RpMergeResult.merge_segment_start == body.merge_segment_start,
            RpMergeResult.merge_segment_end == body.merge_segment_end,
        )
        .first()
    )

    if existing:
        existing.run_id = run.id
        existing.expected_result = payload
        existing.round_start = round_start
        existing.round_end = round_end
        existing.top_k = body.top_k
        existing.temperature = body.temperature
        row = existing
    else:
        row = RpMergeResult(
            run_id=run.id,
            user_id=body.user_id.strip(),
            role_id=body.role_id.strip(),
            app_name=body.app_name.strip(),
            prompt_version=body.prompt_version.strip(),
            merge_segment_start=body.merge_segment_start,
            merge_segment_end=body.merge_segment_end,
            round_start=round_start,
            round_end=round_end,
            model=model,
            expected_result=payload,
            top_k=body.top_k,
            temperature=body.temperature,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    result = _merge_to_dict(row)
    result["run_group_id"] = run.id
    return result


def list_compress_segments(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str,
    prompt_version: Optional[str] = None,
    model: Optional[str] = None,
    run_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    query = db.query(RpCompressResult).filter(
        *_compress_conv_filter(user_id, role_id, app_name),
    )
    if run_id is not None:
        query = query.filter(RpCompressResult.run_id == run_id)
    if prompt_version:
        query = query.filter(RpCompressResult.prompt_version == prompt_version.strip())
    if model:
        query = query.filter(RpCompressResult.model == model.strip())

    rows = query.order_by(
        RpCompressResult.segment_index.asc(),
        RpCompressResult.id.asc(),
    ).all()
    return [_compress_to_dict(row) for row in rows]


def list_merge_results(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str,
    prompt_version: Optional[str] = None,
    model: Optional[str] = None,
    run_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    query = db.query(RpMergeResult).filter(
        RpMergeResult.user_id == user_id.strip(),
        RpMergeResult.role_id == role_id.strip(),
        RpMergeResult.app_name == app_name.strip(),
    )
    if run_id is not None:
        query = query.filter(RpMergeResult.run_id == run_id)
    if prompt_version:
        query = query.filter(RpMergeResult.prompt_version == prompt_version.strip())
    if model:
        query = query.filter(RpMergeResult.model == model.strip())

    rows = query.order_by(
        RpMergeResult.merge_segment_start.asc(),
        RpMergeResult.merge_segment_end.asc(),
        RpMergeResult.id.asc(),
    ).all()
    return [_merge_to_dict(row) for row in rows]


def _aggregate_compress_view(segments: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not segments:
        return None
    last = segments[-1]
    result: dict[str, Any] = {
        "history_segment": last["expected_result"].get("history_segment", ""),
        "memory_state": last["expected_result"].get("memory_state", {}),
    }
    if len(segments) > 1:
        result["pipeline_segments"] = [
            {
                "start_round": seg["round_start"],
                "end_round": seg["round_end"],
                "history_segment": seg["expected_result"].get("history_segment", ""),
                "memory_state": seg["expected_result"].get("memory_state", {}),
            }
            for seg in segments
        ]
    return result


def _build_model_runs(
    compress_rows: list[RpCompressResult],
    merge_rows: list[RpMergeResult],
) -> list[dict[str, Any]]:
    by_model: dict[str, dict[str, Any]] = {}

    for row in compress_rows:
        model = row.model or ""
        slot = by_model.setdefault(
            model,
            {
                "model": model,
                "compress_segments": [],
                "merge_results": [],
                "compress": None,
                "merge": None,
                "compress_record_id": None,
                "merge_record_id": None,
                "compress_run": None,
                "merge_run": None,
                "latest_updated_at": None,
            },
        )
        seg_dict = _compress_to_dict(row)
        slot["compress_segments"].append(seg_dict)
        ts = row.updated_at.isoformat() if row.updated_at else None
        if ts and (not slot["latest_updated_at"] or ts > slot["latest_updated_at"]):
            slot["latest_updated_at"] = ts

    for row in merge_rows:
        model = row.model or ""
        slot = by_model.setdefault(
            model,
            {
                "model": model,
                "compress_segments": [],
                "merge_results": [],
                "compress": None,
                "merge": None,
                "compress_record_id": None,
                "merge_record_id": None,
                "compress_run": None,
                "merge_run": None,
                "latest_updated_at": None,
            },
        )
        merge_dict = _merge_to_dict(row)
        slot["merge_results"].append(merge_dict)
        ts = row.updated_at.isoformat() if row.updated_at else None
        if ts and (not slot["latest_updated_at"] or ts > slot["latest_updated_at"]):
            slot["latest_updated_at"] = ts

    runs: list[dict[str, Any]] = []
    for slot in by_model.values():
        if not (slot["model"] or "").strip():
            continue
        slot["compress_segments"].sort(key=lambda item: item["segment_index"])
        slot["merge_results"].sort(
            key=lambda item: (item["merge_segment_start"], item["merge_segment_end"]),
        )
        slot["compress"] = _aggregate_compress_view(slot["compress_segments"])
        if slot["compress_segments"]:
            latest_compress = slot["compress_segments"][-1]
            slot["compress_record_id"] = latest_compress["id"]
            slot["compress_run"] = {
                "prompt_version": latest_compress["prompt_version"],
                "model": latest_compress["model"],
                "top_k": latest_compress["top_k"],
                "temperature": latest_compress["temperature"],
                "updated_at": latest_compress.get("updated_at"),
            }
        if slot["merge_results"]:
            latest_merge = slot["merge_results"][-1]
            slot["merge"] = latest_merge["expected_result"]
            slot["merge_record_id"] = latest_merge["id"]
            slot["merge_run"] = {
                "prompt_version": latest_merge["prompt_version"],
                "model": latest_merge["model"],
                "top_k": latest_merge["top_k"],
                "temperature": latest_merge["temperature"],
                "updated_at": latest_merge.get("updated_at"),
            }
        if slot["compress_segments"] or slot["merge_results"]:
            runs.append(slot)

    return sorted(runs, key=lambda item: item["latest_updated_at"] or "", reverse=True)


def _pick_model_run(model_runs: list[dict[str, Any]], model: Optional[str]) -> dict[str, Any] | None:
    if not model_runs:
        return None
    if model:
        for item in model_runs:
            if item["model"] == model:
                return item
        return None
    return model_runs[0]


def _resolve_run_id(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str,
    run_id: Optional[int],
) -> int:
    if run_id is not None:
        exists = (
            db.query(RpTestRun.id)
            .filter(
                RpTestRun.id == run_id,
                *_conversation_filter(user_id, role_id, app_name),
            )
            .first()
        )
        if not exists:
            raise HTTPException(status_code=404, detail="RP history not found")
        return run_id

    row = (
        db.query(RpTestRun)
        .filter(*_conversation_filter(user_id, role_id, app_name))
        .order_by(RpTestRun.updated_at.desc(), RpTestRun.id.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="RP history not found")
    return row.id


def list_rp_history(
    db: Session,
    *,
    user_id: Optional[str] = None,
    role_id: Optional[str] = None,
    role_name: Optional[str] = None,
) -> list[dict[str, Any]]:
    query = db.query(RpTestRun)
    if user_id:
        keyword = user_id.strip()
        if keyword:
            query = query.filter(RpTestRun.user_id.contains(keyword))
    if role_id:
        keyword = role_id.strip()
        if keyword:
            query = query.filter(RpTestRun.role_id.contains(keyword))
    if role_name:
        keyword = role_name.strip()
        if keyword:
            query = query.filter(RpTestRun.role_name.contains(keyword))

    runs = query.order_by(RpTestRun.updated_at.desc(), RpTestRun.id.desc()).all()
    results: list[dict[str, Any]] = []

    for run in runs:
        compress_rows = (
            db.query(RpCompressResult)
            .filter(RpCompressResult.run_id == run.id)
            .all()
        )
        merge_rows = (
            db.query(RpMergeResult)
            .filter(RpMergeResult.run_id == run.id)
            .all()
        )
        model_runs = _build_model_runs(compress_rows, merge_rows)
        round_start = 1
        round_end = 10
        if compress_rows:
            round_start = min(row.round_start for row in compress_rows)
            round_end = max(row.round_end for row in compress_rows)
        elif merge_rows:
            round_start = min(row.round_start for row in merge_rows)
            round_end = max(row.round_end for row in merge_rows)

        latest_ts = run.updated_at.isoformat() if run.updated_at else None
        for row in compress_rows + merge_rows:
            ts = row.updated_at.isoformat() if row.updated_at else None
            if ts and (not latest_ts or ts > latest_ts):
                latest_ts = ts

        results.append(
            {
                "conversation_key": _conversation_key(run.user_id, run.role_id, run.app_name),
                "history_key": _history_key(run.user_id, run.role_id, run.app_name, run.id),
                "run_group_id": run.id,
                "run_id": run.id,
                "user_id": run.user_id,
                "role_id": run.role_id,
                "app_name": run.app_name,
                "role_name": run.role_name,
                "prompt_version": run.prompt_version or "",
                "has_compress": len(compress_rows) > 0,
                "has_merge": len(merge_rows) > 0,
                "round_start": round_start,
                "round_end": round_end,
                "latest_updated_at": latest_ts,
                "model_count": len(model_runs),
            },
        )

    return results


def get_rp_history_detail(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str,
    run_group_id: Optional[int] = None,
    run_id: Optional[int] = None,
    model: Optional[str] = None,
) -> dict[str, Any]:
    resolved_run_id = _resolve_run_id(
        db,
        user_id=user_id,
        role_id=role_id,
        app_name=app_name,
        run_id=run_group_id or run_id,
    )
    run = (
        db.query(RpTestRun)
        .filter(RpTestRun.id == resolved_run_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="RP history not found")

    compress_rows = (
        db.query(RpCompressResult)
        .filter(RpCompressResult.run_id == resolved_run_id)
        .order_by(RpCompressResult.segment_index.asc())
        .all()
    )
    merge_rows = (
        db.query(RpMergeResult)
        .filter(RpMergeResult.run_id == resolved_run_id)
        .order_by(
            RpMergeResult.merge_segment_start.asc(),
            RpMergeResult.merge_segment_end.asc(),
        )
        .all()
    )
    model_runs = _build_model_runs(compress_rows, merge_rows)
    picked = _pick_model_run(model_runs, model.strip() if model else None)

    round_start = 1
    round_end = 10
    if compress_rows:
        round_start = min(row.round_start for row in compress_rows)
        round_end = max(row.round_end for row in compress_rows)
    elif merge_rows:
        round_start = min(row.round_start for row in merge_rows)
        round_end = max(row.round_end for row in merge_rows)

    return {
        "conversation_key": _conversation_key(user_id, role_id, app_name),
        "history_key": _history_key(user_id, role_id, app_name, resolved_run_id),
        "run_group_id": resolved_run_id,
        "run_id": resolved_run_id,
        "user_id": user_id,
        "role_id": role_id,
        "app_name": app_name,
        "role_name": run.role_name,
        "prompt_version": run.prompt_version or "",
        "round_start": round_start,
        "round_end": round_end,
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


def delete_rp_history(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str,
    run_group_id: int,
) -> dict[str, Any]:
    resolved_run_id = _resolve_run_id(
        db,
        user_id=user_id,
        role_id=role_id,
        app_name=app_name,
        run_id=run_group_id,
    )
    compress_rows = (
        db.query(RpCompressResult)
        .filter(RpCompressResult.run_id == resolved_run_id)
        .all()
    )
    merge_rows = (
        db.query(RpMergeResult)
        .filter(RpMergeResult.run_id == resolved_run_id)
        .all()
    )
    run = db.query(RpTestRun).filter(RpTestRun.id == resolved_run_id).first()
    if not run and not compress_rows and not merge_rows:
        raise HTTPException(status_code=404, detail="RP history not found")

    deleted_ids = [row.id for row in compress_rows + merge_rows]
    if run:
        deleted_ids.append(run.id)
    for row in compress_rows + merge_rows:
        db.delete(row)
    if run:
        db.delete(run)
    db.commit()

    return {
        "ok": True,
        "run_group_id": resolved_run_id,
        "deleted_ids": deleted_ids,
        "deleted_count": len(deleted_ids),
    }


def delete_rp_history_models(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str,
    run_group_id: int,
    models: list[str],
) -> dict[str, Any]:
    model_names = [m.strip() for m in models if m and m.strip()]
    if not model_names:
        raise HTTPException(status_code=400, detail="models is required")

    resolved_run_id = _resolve_run_id(
        db,
        user_id=user_id,
        role_id=role_id,
        app_name=app_name,
        run_id=run_group_id,
    )
    compress_rows = (
        db.query(RpCompressResult)
        .filter(
            RpCompressResult.run_id == resolved_run_id,
            RpCompressResult.model.in_(model_names),
        )
        .all()
    )
    merge_rows = (
        db.query(RpMergeResult)
        .filter(
            RpMergeResult.run_id == resolved_run_id,
            RpMergeResult.model.in_(model_names),
        )
        .all()
    )
    if not compress_rows and not merge_rows:
        raise HTTPException(status_code=404, detail="RP test model records not found")

    deleted_ids = [row.id for row in compress_rows + merge_rows]
    for row in compress_rows + merge_rows:
        db.delete(row)
    db.commit()

    return {
        "ok": True,
        "run_group_id": resolved_run_id,
        "models": model_names,
        "deleted_ids": deleted_ids,
        "deleted_count": len(deleted_ids),
    }
