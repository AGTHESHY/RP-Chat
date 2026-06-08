"""RP 测试异步任务执行器。"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from chat_completion_client import stream_chat_completion
from chat_qa_service import get_chat_qa_conversation
from conversation_payload import (
    build_history_merge_payload,
    build_segment_compress_payload,
    get_segment_round_range,
    parse_model_json,
    pick_consecutive_segments,
    segment_range_key,
    validate_round_range,
)
from database import SessionLocal
from memory_pipeline import pipeline_step_label, plan_memory_pipeline
from rp_test_job_service import (
    get_rp_test_job,
    list_running_rp_test_job_ids,
    mark_job_done,
    mark_job_error,
    save_rp_test_job,
)
from rp_test_result_service import (
    RpCompressSaveRequest,
    RpMergeSaveRequest,
    list_compress_segments,
    list_merge_results,
    save_compress,
    save_merge,
)
from version_service import get_prompt_content

logger = logging.getLogger(__name__)

_running_tasks: dict[str, asyncio.Task] = {}


def _step_to_result(
    *,
    prompt_type: str,
    response: dict[str, Any],
    raw_content: str,
    reasoning_content: str,
    step_label: str,
) -> dict[str, Any]:
    return {
        "promptType": prompt_type,
        "response": response,
        "rawContent": raw_content,
        "reasoningContent": reasoning_content,
        "stepLabel": step_label,
    }


def _rebuild_model_bundles(job: dict[str, Any]) -> None:
    bundles: list[dict[str, Any]] = []
    for model in job["models"]:
        ms = job["progress"]["model_states"][model]
        if ms.get("error"):
            bundles.append({"model": model, "steps": ms.get("steps", []), "error": ms["error"]})
        else:
            bundles.append({"model": model, "steps": ms.get("steps", [])})
    job["progress"]["model_bundles"] = bundles


async def _load_system_prompt(db: Session, version: str, prompt_type: str, lang: str) -> str:
    data = get_prompt_content(db, version, prompt_type, lang, include_nsfw=False)
    return str(data.get("content") or "")


async def _execute_compress_step(
    *,
    db: Session,
    job: dict[str, Any],
    model: str,
    step: dict[str, Any],
    ms: dict[str, Any],
    messages: list[dict[str, Any]],
    compress_system: str,
) -> None:
    conv = job["conversation"]
    segment = step["segment"]
    start, end = segment["start"], segment["end"]
    payload = build_segment_compress_payload(
        messages,
        conv,
        start,
        end,
        ms.get("memory_state") or {},
    )
    config = job["model_configs"][model]
    resp = await stream_chat_completion(
        base_url=config["base_url"],
        api_key=config["api_key"],
        model=config.get("model") or model,
        system_prompt=compress_system,
        user_content=json.dumps(payload, ensure_ascii=False, indent=2),
        temperature=float(config.get("temperature", 0.3)),
        top_k=config.get("top_k"),
        extra_body=config.get("extra_body"),
    )
    step_label = pipeline_step_label(step)  # type: ignore[arg-type]
    raw = resp.get("raw_content") or resp.get("error") or resp.get("raw_text") or ""
    ms["steps"].append(
        _step_to_result(
            prompt_type="segment_compress",
            response=resp,
            raw_content=raw,
            reasoning_content=resp.get("reasoning_content") or "",
            step_label=step_label,
        )
    )
    if resp.get("status") != 200:
        raise RuntimeError(f"{step_label} 失败: HTTP {resp.get('status')}")

    parsed = parse_model_json(raw)
    if not parsed:
        raise RuntimeError(f"{step_label} 返回非合法 JSON")

    history_segment = str(parsed.get("history_segment", "")).strip()
    if not history_segment:
        raise RuntimeError(f"{step_label} 缺少 history_segment")

    ms["memory_state"] = parsed.get("memory_state") or {}
    item = {
        "id": step["segmentIndex"],
        "start_round": start,
        "end_round": end,
        "history_segment": history_segment,
    }
    outputs = ms.setdefault("segment_outputs", {})
    outputs[segment_range_key(start, end)] = item
    ms.setdefault("compress_saves", []).append(
        {"segmentIndex": step["segmentIndex"], "parsed": parsed}
    )


async def _execute_merge_step(
    *,
    job: dict[str, Any],
    model: str,
    step: dict[str, Any],
    ms: dict[str, Any],
    merge_system: str,
) -> None:
    merge_items: list[dict[str, Any]] = []
    for segment in step["segments"]:
        key = segment_range_key(segment["start"], segment["end"])
        found = (ms.get("segment_outputs") or {}).get(key)
        if not found:
            raise RuntimeError(f"合并步骤缺少 Segment {segment['start']}-{segment['end']} 的压缩结果")
        merge_items.append(found)

    payload = build_history_merge_payload(merge_items, ms.get("history_memory") or "")
    config = job["model_configs"][model]
    resp = await stream_chat_completion(
        base_url=config["base_url"],
        api_key=config["api_key"],
        model=config.get("model") or model,
        system_prompt=merge_system,
        user_content=json.dumps(payload, ensure_ascii=False, indent=2),
        temperature=float(config.get("temperature", 0.3)),
        top_k=config.get("top_k"),
        extra_body=config.get("extra_body"),
    )
    step_label = pipeline_step_label(step)  # type: ignore[arg-type]
    raw = resp.get("raw_content") or resp.get("error") or resp.get("raw_text") or ""
    ms["steps"].append(
        _step_to_result(
            prompt_type="history_merge",
            response=resp,
            raw_content=raw,
            reasoning_content=resp.get("reasoning_content") or "",
            step_label=step_label,
        )
    )
    if resp.get("status") != 200:
        raise RuntimeError(f"{step_label} 失败: HTTP {resp.get('status')}")

    parsed = parse_model_json(raw)
    if not parsed or not str(parsed.get("history_memory", "")).strip():
        raise RuntimeError(f"{step_label} 缺少 history_memory")

    ms["history_memory"] = str(parsed["history_memory"])
    ms.setdefault("merge_saves", []).append(
        {
            "mergeSegmentStart": merge_items[0]["id"],
            "mergeSegmentEnd": merge_items[-1]["id"],
            "parsed": parsed,
        }
    )


async def _execute_single_compress(
    *,
    db: Session,
    job: dict[str, Any],
    model: str,
    ms: dict[str, Any],
    messages: list[dict[str, Any]],
    compress_system: str,
) -> None:
    conv = job["conversation"]
    segment_index = int(job.get("segment_index") or 1)
    start, end = get_segment_round_range(segment_index, len(messages))
    validate_round_range(start, end, len(messages))

    old_memory_state: dict[str, Any] = {}
    if segment_index > 1:
        records = list_compress_segments(
            db,
            user_id=conv["user_id"],
            role_id=conv["role_id"],
            app_name=conv["app_name"],
            prompt_version=job["version"],
            model=model,
            run_id=job.get("rp_history_run_id"),
        )
        prev = next((r for r in records if r["segment_index"] == segment_index - 1), None)
        if prev:
            old_memory_state = prev.get("expected_result", {}).get("memory_state") or {}

    payload = build_segment_compress_payload(
        messages, conv, start, end, old_memory_state
    )
    config = job["model_configs"][model]
    step_label = f"Segment 压缩 · 第 {start}-{end} 轮（段 {segment_index}）"
    resp = await stream_chat_completion(
        base_url=config["base_url"],
        api_key=config["api_key"],
        model=config.get("model") or model,
        system_prompt=compress_system,
        user_content=json.dumps(payload, ensure_ascii=False, indent=2),
        temperature=float(config.get("temperature", 0.3)),
        top_k=config.get("top_k"),
        extra_body=config.get("extra_body"),
    )
    raw = resp.get("raw_content") or resp.get("error") or resp.get("raw_text") or ""
    ms["steps"].append(
        _step_to_result(
            prompt_type="segment_compress",
            response=resp,
            raw_content=raw,
            reasoning_content=resp.get("reasoning_content") or "",
            step_label=step_label,
        )
    )
    if resp.get("status") != 200:
        raise RuntimeError(f"{step_label} 失败: HTTP {resp.get('status')}")

    parsed = parse_model_json(raw)
    if not parsed:
        raise RuntimeError(f"{step_label} 返回非合法 JSON")
    ms.setdefault("compress_saves", []).append(
        {"segmentIndex": segment_index, "parsed": parsed}
    )


async def _execute_single_merge(
    *,
    db: Session,
    job: dict[str, Any],
    model: str,
    ms: dict[str, Any],
    merge_system: str,
) -> None:
    conv = job["conversation"]
    records = list_compress_segments(
        db,
        user_id=conv["user_id"],
        role_id=conv["role_id"],
        app_name=conv["app_name"],
        prompt_version=job["version"],
        model=model,
        run_id=job.get("rp_history_run_id"),
    )
    available = sorted(records, key=lambda r: r["segment_index"])
    mergeable = []
    for row in available:
        history_segment = str(row.get("expected_result", {}).get("history_segment", "")).strip()
        if not history_segment:
            raise RuntimeError(f"段 {row['segment_index']} 缺少 history_segment")
        mergeable.append(
            {
                "index": row["segment_index"],
                "start_round": row["round_start"],
                "end_round": row["round_end"],
                "history_segment": history_segment,
            }
        )

    count = int(job.get("merge_segment_count") or 1)
    end_index = int(job.get("merge_segment_end_index") or 1)
    segments = pick_consecutive_segments(mergeable, count, end_index)

    old_history_memory = ""
    try:
        merges = list_merge_results(
            db,
            user_id=conv["user_id"],
            role_id=conv["role_id"],
            app_name=conv["app_name"],
            prompt_version=job["version"],
            model=model,
            run_id=job.get("rp_history_run_id"),
        )
        if merges:
            old_history_memory = str(merges[-1].get("expected_result", {}).get("history_memory", ""))
    except Exception:
        old_history_memory = ""

    payload = build_history_merge_payload(segments, old_history_memory)
    config = job["model_configs"][model]
    step_label = (
        f"History 合并 · 段 {end_index - count + 1}-{end_index} · "
        f"第 {segments[0]['start_round']}-{segments[-1]['end_round']} 轮"
    )
    resp = await stream_chat_completion(
        base_url=config["base_url"],
        api_key=config["api_key"],
        model=config.get("model") or model,
        system_prompt=merge_system,
        user_content=json.dumps(payload, ensure_ascii=False, indent=2),
        temperature=float(config.get("temperature", 0.3)),
        top_k=config.get("top_k"),
        extra_body=config.get("extra_body"),
    )
    raw = resp.get("raw_content") or resp.get("error") or resp.get("raw_text") or ""
    ms["steps"].append(
        _step_to_result(
            prompt_type="history_merge",
            response=resp,
            raw_content=raw,
            reasoning_content=resp.get("reasoning_content") or "",
            step_label=step_label,
        )
    )
    if resp.get("status") != 200:
        raise RuntimeError(f"{step_label} 失败: HTTP {resp.get('status')}")

    parsed = parse_model_json(raw)
    if not parsed or not str(parsed.get("history_memory", "")).strip():
        raise RuntimeError(f"{step_label} 缺少 history_memory")

    ms.setdefault("merge_saves", []).append(
        {
            "mergeSegmentStart": end_index - count + 1,
            "mergeSegmentEnd": end_index,
            "parsed": parsed,
        }
    )


def _finalize_mysql_saves(db: Session, job: dict[str, Any]) -> int:
    saved_count = 0
    run_group_id = job["progress"].get("run_group_id")
    conv = job["conversation"]

    for model in job["models"]:
        ms = job["progress"]["model_states"][model]
        if ms.get("saved_to_mysql") or ms.get("error"):
            continue
        steps = ms.get("steps") or []
        if not steps or any(s.get("response", {}).get("status") != 200 for s in steps):
            continue

        config = job["model_configs"][model]
        try:
            for item in ms.get("compress_saves") or []:
                saved = save_compress(
                    db,
                    RpCompressSaveRequest(
                        user_id=conv["user_id"],
                        role_id=conv["role_id"],
                        app_name=conv["app_name"],
                        role_name=conv.get("role_name", ""),
                        prompt_version=job["version"],
                        segment_index=item["segmentIndex"],
                        expected_result=item["parsed"],
                        model=config.get("model") or model,
                        top_k=config.get("top_k"),
                        temperature=float(config.get("temperature", 0.3)),
                        run_id=run_group_id,
                    ),
                )
                if saved.get("run_group_id") is not None and run_group_id is None:
                    run_group_id = saved["run_group_id"]
                    job["progress"]["run_group_id"] = run_group_id

            for item in ms.get("merge_saves") or []:
                saved = save_merge(
                    db,
                    RpMergeSaveRequest(
                        user_id=conv["user_id"],
                        role_id=conv["role_id"],
                        app_name=conv["app_name"],
                        role_name=conv.get("role_name", ""),
                        prompt_version=job["version"],
                        merge_segment_start=item["mergeSegmentStart"],
                        merge_segment_end=item["mergeSegmentEnd"],
                        expected_result=item["parsed"],
                        model=config.get("model") or model,
                        top_k=config.get("top_k"),
                        temperature=float(config.get("temperature", 0.3)),
                        run_id=run_group_id,
                    ),
                )
                if saved.get("run_group_id") is not None and run_group_id is None:
                    run_group_id = saved["run_group_id"]
                    job["progress"]["run_group_id"] = run_group_id

            ms["saved_to_mysql"] = True
            saved_count += 1
        except Exception as exc:
            ms["error"] = str(exc)
            logger.exception("RP test job mysql save failed for model %s", model)

    job["progress"]["saved_count"] = saved_count
    return saved_count


async def _run_job_loop(job_id: str) -> None:
    db = SessionLocal()
    try:
        while True:
            job = get_rp_test_job(job_id)
            if not job or job.get("status") != "running":
                return

            conv = job["conversation"]
            detail = get_chat_qa_conversation(
                db,
                user_id=conv["user_id"],
                role_id=conv["role_id"],
                app_name=conv["app_name"],
            )
            messages = detail["messages"]
            lang = job.get("lang") or "en"

            compress_system = await _load_system_prompt(db, job["version"], "segment_compress", lang)
            merge_system = await _load_system_prompt(db, job["version"], "history_merge", lang)
            if not compress_system.strip() or not merge_system.strip():
                mark_job_error(job_id, "Segment 压缩或 History 合并 System Prompt 未加载")
                return

            any_progress = False
            test_mode = job.get("test_mode")

            if test_mode == "single":
                for model in job["models"]:
                    ms = job["progress"]["model_states"][model]
                    if ms.get("done") or ms.get("error") or ms.get("step_index", 0) > 0:
                        if ms.get("step_index", 0) > 0 and not ms.get("done"):
                            ms["done"] = True
                        continue
                    try:
                        if job.get("prompt_type") == "history_merge":
                            await _execute_single_merge(
                                db=db, job=job, model=model, ms=ms, merge_system=merge_system
                            )
                        else:
                            await _execute_single_compress(
                                db=db,
                                job=job,
                                model=model,
                                ms=ms,
                                messages=messages,
                                compress_system=compress_system,
                            )
                        ms["step_index"] = 1
                        ms["done"] = True
                        any_progress = True
                    except Exception as exc:
                        ms["error"] = str(exc)
                        ms["done"] = True
            else:
                plan = job.get("plan") or {}
                steps = plan.get("steps") or []
                if job.get("round_range"):
                    validate_round_range(
                        job["round_range"]["start"],
                        job["round_range"]["end"],
                        len(messages),
                    )

                for model in job["models"]:
                    ms = job["progress"]["model_states"][model]
                    if ms.get("done") or ms.get("error"):
                        continue
                    step_index = int(ms.get("step_index") or 0)
                    if step_index >= len(steps):
                        ms["done"] = True
                        continue

                    step = steps[step_index]
                    try:
                        if step["type"] == "compress":
                            await _execute_compress_step(
                                db=db,
                                job=job,
                                model=model,
                                step=step,
                                ms=ms,
                                messages=messages,
                                compress_system=compress_system,
                            )
                        else:
                            await _execute_merge_step(
                                db=db,
                                job=job,
                                model=model,
                                step=step,
                                ms=ms,
                                merge_system=merge_system,
                            )
                        ms["step_index"] = step_index + 1
                        any_progress = True
                    except Exception as exc:
                        ms["error"] = str(exc)
                        ms["done"] = True

            _rebuild_model_bundles(job)
            save_rp_test_job(job)

            all_finished = all(
                job["progress"]["model_states"][m].get("done") for m in job["models"]
            )
            if all_finished:
                saved = _finalize_mysql_saves(db, job)
                _rebuild_model_bundles(job)
                run_group_id = job["progress"].get("run_group_id")
                mark_job_done(job_id, run_group_id)
                logger.info("RP test job %s finished, saved %s models", job_id, saved)
                return

            if not any_progress:
                mark_job_error(job_id, "任务无法继续执行")
                return

            await asyncio.sleep(0.05)
    except Exception as exc:
        logger.exception("RP test job %s failed", job_id)
        mark_job_error(job_id, str(exc))
    finally:
        db.close()


def schedule_rp_test_job(job_id: str) -> None:
    if job_id in _running_tasks and not _running_tasks[job_id].done():
        return
    task = asyncio.create_task(_run_job_loop(job_id))
    _running_tasks[job_id] = task

    def _cleanup(fut: asyncio.Task) -> None:
        _running_tasks.pop(job_id, None)

    task.add_done_callback(_cleanup)


async def resume_running_rp_test_jobs() -> None:
    for job_id in list_running_rp_test_job_ids():
        schedule_rp_test_job(job_id)


def build_job_plan(body: dict[str, Any]) -> tuple[Optional[dict[str, Any]], bool]:
    if body.get("test_mode") != "pipeline":
        return None, False
    rr = body.get("round_range") or {}
    plan = plan_memory_pipeline(int(rr["start"]), int(rr["end"]))
    return plan, plan["hasForcedTailMerge"]
