from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

import redis

from config import (
    BRAIN_KEY_PREFIX,
    REDIS_BRAIN_TTL_SECONDS,
    REDIS_DB,
    REDIS_DRAFT_TTL_SECONDS,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
)

_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
        )
    return _client


def draft_key(version: str) -> str:
    from config import DRAFT_KEY_PREFIX

    return f"{DRAFT_KEY_PREFIX}{version}"


def get_draft(version: str) -> Optional[dict[str, Any]]:
    raw = get_redis().get(draft_key(version))
    if not raw:
        return None
    return json.loads(raw)


def save_draft(version: str, data: dict[str, Any]) -> None:
    get_redis().set(draft_key(version), json.dumps(data, ensure_ascii=False), ex=REDIS_DRAFT_TTL_SECONDS)


def delete_draft(version: str) -> None:
    get_redis().delete(draft_key(version))


def list_draft_versions() -> list[str]:
    from config import DRAFT_KEY_PREFIX

    client = get_redis()
    keys = client.keys(f"{DRAFT_KEY_PREFIX}*")
    prefix_len = len(DRAFT_KEY_PREFIX)
    return sorted(key[prefix_len:] for key in keys)


def _brain_record_key(record_id: int) -> str:
    return f"{BRAIN_KEY_PREFIX}record:{record_id}"


def _brain_index_key(user_id: str, role_id: str, app_name: str) -> str:
    return f"{BRAIN_KEY_PREFIX}index:{user_id}:{role_id}:{app_name}"


def _brain_id_seq_key() -> str:
    return f"{BRAIN_KEY_PREFIX}id_seq"


def _brain_set_opts() -> dict[str, Any]:
    if REDIS_BRAIN_TTL_SECONDS > 0:
        return {"ex": REDIS_BRAIN_TTL_SECONDS}
    return {}


def next_brain_record_id() -> int:
    return int(get_redis().incr(_brain_id_seq_key()))


def save_brain_record(record: dict[str, Any]) -> None:
    record_id = int(record["id"])
    user_id = str(record["user_id"])
    role_id = str(record["role_id"])
    app_name = str(record.get("app_name", ""))
    client = get_redis()
    client.set(
        _brain_record_key(record_id),
        json.dumps(record, ensure_ascii=False),
        **_brain_set_opts(),
    )
    created_ts = record.get("_created_ts")
    if created_ts is None:
        created_ts = time.time()
    client.zadd(_brain_index_key(user_id, role_id, app_name), {str(record_id): float(created_ts)})
    if REDIS_BRAIN_TTL_SECONDS > 0:
        client.expire(_brain_index_key(user_id, role_id, app_name), REDIS_BRAIN_TTL_SECONDS)


def get_brain_record(record_id: int) -> Optional[dict[str, Any]]:
    raw = get_redis().get(_brain_record_key(record_id))
    if not raw:
        return None
    data = json.loads(raw)
    if "_created_ts" in data:
        del data["_created_ts"]
    return data


def delete_brain_record(record_id: int) -> Optional[dict[str, Any]]:
    record = get_brain_record(record_id)
    if not record:
        return None
    user_id = str(record["user_id"])
    role_id = str(record["role_id"])
    app_name = str(record.get("app_name", ""))
    client = get_redis()
    client.delete(_brain_record_key(record_id))
    client.zrem(_brain_index_key(user_id, role_id, app_name), str(record_id))
    return record


def list_brain_record_ids(user_id: str, role_id: str, app_name: str = "") -> list[int]:
    client = get_redis()
    index_key = _brain_index_key(user_id, role_id, app_name)
    ids = client.zrevrange(index_key, 0, -1)
    result: list[int] = []
    for item in ids:
        record_id = int(item)
        if client.exists(_brain_record_key(record_id)):
            result.append(record_id)
        else:
            client.zrem(index_key, item)
    return result


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
