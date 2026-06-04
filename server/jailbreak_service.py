from __future__ import annotations

import json
import re
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from jailbreak_compose import normalize_modules_json, parse_modules_json, validate_content_mode
from models import JailbreakPrompt

_SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
_VERSION_PATTERN = re.compile(r"^v(\d+)$", re.IGNORECASE)


def _row_to_dict(row: JailbreakPrompt) -> dict[str, Any]:
    modules = parse_modules_json(row.modules_json)
    return {
        "id": row.id,
        "scheme_name": row.scheme_name,
        "version": row.version,
        "target_model": row.target_model,
        "content": row.content,
        "content_mode": row.content_mode or "plain",
        "modules_json": modules,
        "changelog": row.changelog,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def validate_scheme_name(name: str) -> str:
    value = name.strip()
    if not value or len(value) > 64:
        raise HTTPException(status_code=400, detail="scheme_name must be 1-64 characters")
    if not _SCHEME_PATTERN.match(value):
        raise HTTPException(
            status_code=400,
            detail="scheme_name must match [a-zA-Z][a-zA-Z0-9_]*",
        )
    return value


def parse_version_number(version: str) -> int:
    match = _VERSION_PATTERN.match(version.strip())
    if not match:
        raise HTTPException(status_code=400, detail="version must be vN format, e.g. v1")
    return int(match.group(1))


def next_version_label(version: str) -> str:
    return f"v{parse_version_number(version) + 1}"


def compute_next_version_for_scheme(db: Session, scheme_name: str) -> str:
    rows = (
        db.query(JailbreakPrompt.version)
        .filter(JailbreakPrompt.scheme_name == scheme_name)
        .all()
    )
    if not rows:
        return "v1"
    max_num = 0
    for (version,) in rows:
        try:
            max_num = max(max_num, parse_version_number(version))
        except HTTPException:
            continue
    return f"v{max_num + 1}"


def get_jailbreak(db: Session, record_id: int) -> dict[str, Any]:
    row = db.query(JailbreakPrompt).filter(JailbreakPrompt.id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Jailbreak prompt not found")
    return _row_to_dict(row)


def list_jailbreaks(
    db: Session,
    *,
    scheme_name: Optional[str] = None,
    target_model: Optional[str] = None,
) -> list[dict[str, Any]]:
    query = db.query(JailbreakPrompt)
    if scheme_name:
        keyword = scheme_name.strip()
        if keyword:
            query = query.filter(JailbreakPrompt.scheme_name.contains(keyword))
    if target_model:
        keyword = target_model.strip()
        if keyword:
            query = query.filter(JailbreakPrompt.target_model.contains(keyword))
    rows = query.order_by(
        JailbreakPrompt.scheme_name,
        JailbreakPrompt.version,
    ).all()
    return [_row_to_dict(row) for row in rows]


def list_jailbreak_schemes(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(JailbreakPrompt)
        .order_by(JailbreakPrompt.scheme_name, JailbreakPrompt.version)
        .all()
    )
    schemes: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = schemes.setdefault(
            row.scheme_name,
            {
                "scheme_name": row.scheme_name,
                "version_count": 0,
                "latest_version": row.version,
                "latest_id": row.id,
                "target_model": row.target_model,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            },
        )
        entry["version_count"] += 1
        try:
            if parse_version_number(row.version) >= parse_version_number(entry["latest_version"]):
                entry["latest_version"] = row.version
                entry["latest_id"] = row.id
                entry["target_model"] = row.target_model
                entry["updated_at"] = (
                    row.updated_at.isoformat() if row.updated_at else None
                )
        except HTTPException:
            pass
    return sorted(schemes.values(), key=lambda item: item["scheme_name"])


def create_jailbreak(
    db: Session,
    *,
    scheme_name: str,
    target_model: str,
    content: str,
    changelog: str = "",
    version: Optional[str] = None,
    content_mode: str = "plain",
    modules_json: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    scheme = validate_scheme_name(scheme_name)
    target = target_model.strip()
    if not target:
        raise HTTPException(status_code=400, detail="target_model is required")

    version_label = version.strip() if version else compute_next_version_for_scheme(db, scheme)
    parse_version_number(version_label)

    exists = (
        db.query(JailbreakPrompt)
        .filter(
            JailbreakPrompt.scheme_name == scheme,
            JailbreakPrompt.version == version_label,
        )
        .first()
    )
    if exists:
        raise HTTPException(
            status_code=409,
            detail=f"Version {scheme} {version_label} already exists",
        )

    mode = validate_content_mode(content_mode)
    modules_str = normalize_modules_json(modules_json)

    row = JailbreakPrompt(
        scheme_name=scheme,
        version=version_label,
        target_model=target,
        content=content,
        content_mode=mode,
        modules_json=modules_str,
        changelog=changelog or "",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def update_jailbreak(
    db: Session,
    record_id: int,
    *,
    target_model: Optional[str] = None,
    content: Optional[str] = None,
    changelog: Optional[str] = None,
    content_mode: Optional[str] = None,
    modules_json: Optional[dict[str, Any]] = None,
    modules_json_set: bool = False,
) -> dict[str, Any]:
    row = db.query(JailbreakPrompt).filter(JailbreakPrompt.id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Jailbreak prompt not found")

    if target_model is not None:
        target = target_model.strip()
        if not target:
            raise HTTPException(status_code=400, detail="target_model cannot be empty")
        row.target_model = target
    if content is not None:
        row.content = content
    if changelog is not None:
        row.changelog = changelog
    if content_mode is not None:
        row.content_mode = validate_content_mode(content_mode)
    if modules_json_set:
        row.modules_json = normalize_modules_json(modules_json)

    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def delete_jailbreak(db: Session, record_id: int) -> dict[str, Any]:
    row = db.query(JailbreakPrompt).filter(JailbreakPrompt.id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Jailbreak prompt not found")
    data = _row_to_dict(row)
    db.delete(row)
    db.commit()
    return {"ok": True, "deleted": data}


def fork_next_version(db: Session, record_id: int) -> dict[str, Any]:
    row = db.query(JailbreakPrompt).filter(JailbreakPrompt.id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Jailbreak prompt not found")

    next_label = compute_next_version_for_scheme(db, row.scheme_name)
    changelog = f"Forked from {row.version}"

    new_row = JailbreakPrompt(
        scheme_name=row.scheme_name,
        version=next_label,
        target_model=row.target_model,
        content=row.content,
        content_mode=row.content_mode or "plain",
        modules_json=row.modules_json,
        changelog=changelog,
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return _row_to_dict(new_row)
