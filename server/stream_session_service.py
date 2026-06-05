"""流式会话暂存：切换页面时 Redis 保存进度，返回时可恢复展示。"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from config import REDIS_STREAM_TTL_SECONDS, STREAM_ACTIVE_PREFIX, STREAM_KEY_PREFIX
from redis_client import get_redis


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_key(session_id: str) -> str:
    return f"{STREAM_KEY_PREFIX}{session_id}"


def _active_key(scope: str, task_key: str) -> str:
    return f"{STREAM_ACTIVE_PREFIX}{scope}:{task_key}"


def _set_opts(ttl: int | None = None) -> dict[str, Any]:
    seconds = REDIS_STREAM_TTL_SECONDS if ttl is None else ttl
    if seconds > 0:
        return {"ex": seconds}
    return {}


def create_stream_session(
    scope: str,
    task_key: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    client = get_redis()
    active_key = _active_key(scope, task_key)
    old_id = client.get(active_key)
    if old_id:
        client.delete(_session_key(old_id))

    session_id = secrets.token_hex(16)
    data: dict[str, Any] = {
        "id": session_id,
        "scope": scope,
        "task_key": task_key,
        "status": "running",
        "raw_content": "",
        "reasoning_content": "",
        "meta": meta or {},
        "error": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    opts = _set_opts()
    client.set(_session_key(session_id), json.dumps(data, ensure_ascii=False), **opts)
    client.set(active_key, session_id, **opts)
    return data


def get_stream_session(session_id: str) -> Optional[dict[str, Any]]:
    raw = get_redis().get(_session_key(session_id))
    if not raw:
        return None
    return json.loads(raw)


def patch_stream_session(session_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    client = get_redis()
    key = _session_key(session_id)
    raw = client.get(key)
    if not raw:
        raise ValueError("stream session not found")
    data: dict[str, Any] = json.loads(raw)
    for field in (
        "raw_content",
        "reasoning_content",
        "status",
        "error",
        "meta",
        "parsed_result",
    ):
        if field in patch:
            data[field] = patch[field]
    data["updated_at"] = _now_iso()

    ttl = client.ttl(key)
    opts = _set_opts(ttl if isinstance(ttl, int) and ttl > 0 else None)
    client.set(key, json.dumps(data, ensure_ascii=False), **opts)

    if data.get("status") in ("done", "error", "cancelled"):
        scope = data.get("scope")
        task_key = data.get("task_key")
        if scope and task_key:
            active_key = _active_key(scope, task_key)
            if client.get(active_key) == session_id:
                client.delete(active_key)
    return data


def get_active_stream_session(scope: str, task_key: str) -> Optional[dict[str, Any]]:
    session_id = get_redis().get(_active_key(scope, task_key))
    if not session_id:
        return None
    return get_stream_session(session_id)
