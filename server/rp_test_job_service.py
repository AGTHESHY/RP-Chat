"""RP 测试异步任务 Redis 暂存。"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from config import (
    REDIS_RP_TEST_JOB_TTL_SECONDS,
    RP_TEST_ACTIVE_PREFIX,
    RP_TEST_JOB_PREFIX,
    RP_TEST_RUNNING_SET,
)
from redis_client import get_redis


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_key(job_id: str) -> str:
    return f"{RP_TEST_JOB_PREFIX}{job_id}"


def _active_key(conversation_key: str) -> str:
    return f"{RP_TEST_ACTIVE_PREFIX}{conversation_key}"


def _set_opts(ttl: int | None = None) -> dict[str, Any]:
    seconds = REDIS_RP_TEST_JOB_TTL_SECONDS if ttl is None else ttl
    if seconds > 0:
        return {"ex": seconds}
    return {}


def _empty_model_state() -> dict[str, Any]:
    return {
        "step_index": 0,
        "memory_state": {},
        "history_memory": "",
        "segment_outputs": {},
        "steps": [],
        "compress_saves": [],
        "merge_saves": [],
        "error": "",
        "done": False,
        "saved_to_mysql": False,
    }


def create_rp_test_job(body: dict[str, Any]) -> dict[str, Any]:
    client = get_redis()
    conversation_key = str(body["conversation_key"])
    active_key = _active_key(conversation_key)

    old_id = client.get(active_key)
    if old_id:
        old_job = get_rp_test_job(old_id)
        if old_job and old_job.get("status") == "running":
            delete_rp_test_job(old_id)

    job_id = secrets.token_hex(16)
    models: list[str] = body["models"]
    model_states = {model: _empty_model_state() for model in models}

    job: dict[str, Any] = {
        "id": job_id,
        "status": "running",
        "conversation_key": conversation_key,
        "conversation": body["conversation"],
        "test_mode": body["test_mode"],
        "prompt_type": body["prompt_type"],
        "round_range": body.get("round_range"),
        "segment_index": body.get("segment_index"),
        "merge_segment_count": body.get("merge_segment_count"),
        "merge_segment_end_index": body.get("merge_segment_end_index"),
        "version": body["version"],
        "lang": body.get("lang", "en"),
        "rp_history_run_id": body.get("rp_history_run_id"),
        "models": models,
        "model_configs": body["model_configs"],
        "plan": body.get("plan"),
        "has_forced_tail_merge": bool(body.get("has_forced_tail_merge")),
        "progress": {
            "model_states": model_states,
            "model_bundles": [],
            "run_group_id": body.get("rp_history_run_id"),
            "saved_count": 0,
        },
        "error": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    opts = _set_opts()
    client.set(_job_key(job_id), json.dumps(job, ensure_ascii=False), **opts)
    client.set(active_key, job_id, **opts)
    client.sadd(RP_TEST_RUNNING_SET, job_id)
    if REDIS_RP_TEST_JOB_TTL_SECONDS > 0:
        client.expire(RP_TEST_RUNNING_SET, REDIS_RP_TEST_JOB_TTL_SECONDS)
    return job


def get_rp_test_job(job_id: str) -> Optional[dict[str, Any]]:
    raw = get_redis().get(_job_key(job_id))
    if not raw:
        return None
    return json.loads(raw)


def save_rp_test_job(job: dict[str, Any]) -> dict[str, Any]:
    client = get_redis()
    job_id = job["id"]
    key = _job_key(job_id)
    job["updated_at"] = _now_iso()
    ttl = client.ttl(key)
    opts = _set_opts(ttl if isinstance(ttl, int) and ttl > 0 else None)
    client.set(key, json.dumps(job, ensure_ascii=False), **opts)
    return job


def delete_rp_test_job(job_id: str) -> None:
    client = get_redis()
    job = get_rp_test_job(job_id)
    if job:
        conversation_key = job.get("conversation_key")
        if conversation_key:
            active_key = _active_key(conversation_key)
            if client.get(active_key) == job_id:
                client.delete(active_key)
    client.delete(_job_key(job_id))
    client.srem(RP_TEST_RUNNING_SET, job_id)


def get_active_rp_test_job(conversation_key: str) -> Optional[dict[str, Any]]:
    session_id = get_redis().get(_active_key(conversation_key))
    if not session_id:
        return None
    return get_rp_test_job(session_id)


def list_running_rp_test_job_ids() -> list[str]:
    client = get_redis()
    ids = client.smembers(RP_TEST_RUNNING_SET)
    result: list[str] = []
    for job_id in ids:
        job = get_rp_test_job(job_id)
        if job and job.get("status") == "running":
            result.append(job_id)
        else:
            client.srem(RP_TEST_RUNNING_SET, job_id)
    return result


def cancel_rp_test_job(job_id: str) -> Optional[dict[str, Any]]:
    job = get_rp_test_job(job_id)
    if not job:
        return None
    job["status"] = "cancelled"
    job["error"] = "任务已取消"
    save_rp_test_job(job)
    delete_rp_test_job(job_id)
    return job


def mark_job_done(job_id: str, run_group_id: Optional[int] = None) -> None:
    client = get_redis()
    job = get_rp_test_job(job_id)
    if not job:
        return
    job["status"] = "done"
    if run_group_id is not None:
        job["progress"]["run_group_id"] = run_group_id
    save_rp_test_job(job)
    conversation_key = job.get("conversation_key")
    if conversation_key:
        active_key = _active_key(conversation_key)
        if client.get(active_key) == job_id:
            client.delete(active_key)
    client.srem(RP_TEST_RUNNING_SET, job_id)


def mark_job_error(job_id: str, error: str) -> None:
    job = get_rp_test_job(job_id)
    if not job:
        return
    job["status"] = "error"
    job["error"] = error
    save_rp_test_job(job)
    get_redis().srem(RP_TEST_RUNNING_SET, job_id)
