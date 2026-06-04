from __future__ import annotations

import json
from typing import Any, Optional

import redis

from config import REDIS_DB, REDIS_DRAFT_TTL_SECONDS, REDIS_HOST, REDIS_PASSWORD, REDIS_PORT

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
