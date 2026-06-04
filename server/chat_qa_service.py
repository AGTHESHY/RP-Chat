from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import ChatQaCase


def _row_to_dict(row: ChatQaCase) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "role_id": row.role_id,
        "role_name": row.role_name,
        "app_name": row.app_name,
        "question": row.question,
        "answer": row.answer,
        "status": row.status,
        "u_time": row.u_time,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _conversation_key(user_id: str, role_id: str, app_name: str) -> str:
    return f"{user_id}|{role_id}|{app_name}"


def _apply_filters(
    query,
    *,
    user_id: Optional[str] = None,
    role_id: Optional[str] = None,
    role_name: Optional[str] = None,
):
    if user_id:
        keyword = user_id.strip()
        if keyword:
            query = query.filter(ChatQaCase.user_id.contains(keyword))
    if role_id:
        keyword = role_id.strip()
        if keyword:
            query = query.filter(ChatQaCase.role_id.contains(keyword))
    if role_name:
        keyword = role_name.strip()
        if keyword:
            query = query.filter(ChatQaCase.role_name.contains(keyword))
    return query


def list_chat_qa_conversations(
    db: Session,
    *,
    user_id: Optional[str] = None,
    role_id: Optional[str] = None,
    role_name: Optional[str] = None,
) -> list[dict[str, Any]]:
    query = _apply_filters(
        db.query(ChatQaCase),
        user_id=user_id,
        role_id=role_id,
        role_name=role_name,
    )
    rows = query.order_by(ChatQaCase.u_time.asc(), ChatQaCase.id.asc()).all()

    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row.user_id, row.role_id, row.app_name)
        entry = grouped.setdefault(
            key,
            {
                "conversation_key": _conversation_key(row.user_id, row.role_id, row.app_name),
                "user_id": row.user_id,
                "role_id": row.role_id,
                "role_name": row.role_name,
                "app_name": row.app_name,
                "message_count": 0,
                "latest_u_time": row.u_time,
            },
        )
        entry["message_count"] += 1
        entry["role_name"] = row.role_name
        if row.u_time >= entry["latest_u_time"]:
            entry["latest_u_time"] = row.u_time

    conversations = sorted(
        grouped.values(),
        key=lambda item: (-item["latest_u_time"], item["user_id"], item["role_id"]),
    )
    return conversations


def get_chat_qa_conversation(
    db: Session,
    *,
    user_id: str,
    role_id: str,
    app_name: str,
) -> dict[str, Any]:
    rows = (
        db.query(ChatQaCase)
        .filter(
            ChatQaCase.user_id == user_id,
            ChatQaCase.role_id == role_id,
            ChatQaCase.app_name == app_name,
        )
        .order_by(ChatQaCase.u_time.asc(), ChatQaCase.id.asc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Conversation not found")

    first = rows[0]
    return {
        "conversation_key": _conversation_key(user_id, role_id, app_name),
        "user_id": user_id,
        "role_id": role_id,
        "role_name": first.role_name,
        "app_name": app_name,
        "message_count": len(rows),
        "messages": [_row_to_dict(row) for row in rows],
    }


def list_chat_qa_cases(
    db: Session,
    *,
    user_id: Optional[str] = None,
    role_id: Optional[str] = None,
    role_name: Optional[str] = None,
) -> list[dict[str, Any]]:
    query = _apply_filters(db.query(ChatQaCase), user_id=user_id, role_id=role_id, role_name=role_name)
    rows = query.order_by(ChatQaCase.u_time.asc(), ChatQaCase.id.asc()).all()
    return [_row_to_dict(row) for row in rows]


def get_chat_qa_case(db: Session, record_id: int) -> dict[str, Any]:
    row = db.query(ChatQaCase).filter(ChatQaCase.id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Chat QA case not found")
    return _row_to_dict(row)
