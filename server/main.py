"""RP Chat Prompt Manager & Test API."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine, get_db
from migrate_schema import (
    migrate_chat_qa_schema,
    migrate_jailbreak_schema,
    migrate_prompt_drop_filename,
    migrate_prompt_sfw_nsfw,
    migrate_prompt_test_result_schema,
    migrate_prompt_whitespace,
    migrate_rp_eval_schema,
    migrate_version_schema,
)
from brain_service import (
    BrainSaveRequest,
    create_brain_analysis,
    delete_brain_analysis,
    get_brain_analysis,
    list_brain_analyses,
)
from rp_eval_service import (
    RpEvalSaveRequest,
    create_rp_eval,
    delete_rp_eval,
    get_rp_eval,
    list_rp_evaluations,
)
from seed_bootstrap import bootstrap_seed_data
from prompt_test_result_service import (
    PromptTestResultSaveRequest,
    get_prompt_test_result,
    get_prompt_test_result_for_conversation,
    get_rp_history_detail,
    list_prompt_test_results,
    list_rp_history,
    save_prompt_test_result,
)
from chat_qa_service import (
    get_chat_qa_case,
    get_chat_qa_conversation,
    list_chat_qa_cases,
    list_chat_qa_conversations,
)
from jailbreak_service import (
    create_jailbreak,
    delete_jailbreak,
    fork_next_version,
    get_jailbreak,
    list_jailbreak_schemes,
    list_jailbreaks,
    update_jailbreak,
)
from version_service import (
    commit_version,
    create_version_draft,
    delete_version_tree,
    discard_draft,
    get_doc_content,
    get_prompt_content,
    get_version_meta,
    list_versions,
    normalize_base_url,
    translate_draft,
    update_draft,
    validate_writable,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        migrate_prompt_sfw_nsfw(db)
        migrate_prompt_whitespace(db)
        migrate_prompt_drop_filename(db)
        migrate_version_schema(db)
        migrate_jailbreak_schema(db)
        migrate_chat_qa_schema(db)
        migrate_prompt_test_result_schema(db)
        migrate_rp_eval_schema(db)
        bootstrap_seed_data(db)
    finally:
        db.close()
    yield


app = FastAPI(title="RP Chat Prompt API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateVersionRequest(BaseModel):
    version: str
    base_version: Optional[str] = None


class DraftPromptUpdate(BaseModel):
    prompt_type: Optional[str] = None
    lang: Optional[str] = None
    content_sfw: Optional[str] = None
    content_nsfw: Optional[str] = None
    doc_content: Optional[str] = None


class TranslateRequest(BaseModel):
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.3


class ContentUpdateRequest(BaseModel):
    content: str


class JailbreakCreateRequest(BaseModel):
    scheme_name: str
    target_model: str
    content: str
    changelog: str = ""
    version: Optional[str] = None
    content_mode: str = "plain"
    modules_json: Optional[dict[str, Any]] = None


class JailbreakUpdateRequest(BaseModel):
    target_model: Optional[str] = None
    content: Optional[str] = None
    changelog: Optional[str] = None
    content_mode: Optional[str] = None
    modules_json: Optional[dict[str, Any]] = None


class ChatCompletionRequest(BaseModel):
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.3
    top_k: Optional[int] = None
    system_prompt: str
    user_content: str
    max_completion_tokens: Optional[int] = Field(default=None, ge=1)
    timeout_seconds: Optional[float] = None
    extra_body: Optional[dict[str, Any]] = None


def _resolve_chat_timeout(timeout_seconds: Optional[float]) -> float:
    """流式空闲超时：连续无数据的最长等待秒数（非总时长）。"""
    if timeout_seconds is None:
        return 120.0
    return max(30.0, min(600.0, float(timeout_seconds)))


def _stream_httpx_timeout(idle_seconds: float) -> httpx.Timeout:
    """流式上游：read 为 chunk 间空闲超时，不设总时长上限。"""
    return httpx.Timeout(connect=30.0, read=idle_seconds, write=60.0, pool=30.0)


def _resolve_max_completion_tokens(max_completion_tokens: Optional[int]) -> int:
    if max_completion_tokens is None:
        return 4096
    return max(1024, min(16384, int(max_completion_tokens)))


@app.get("/api/versions")
def api_list_versions(db: Session = Depends(get_db)) -> dict[str, Any]:
    return list_versions(db)


@app.post("/api/versions")
def api_create_version(body: CreateVersionRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    return create_version_draft(db, body.version, body.base_version)


@app.get("/api/versions/{version}")
def api_get_version(version: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_version_meta(db, version)


@app.get("/api/versions/{version}/prompts/{prompt_type}/{lang}")
def api_get_version_prompt(
    version: str,
    prompt_type: str,
    lang: str,
    include_nsfw: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_prompt_content(db, version, prompt_type, lang, include_nsfw=include_nsfw)


@app.get("/api/versions/{version}/docs")
def api_get_version_doc(version: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_doc_content(db, version)


@app.put("/api/versions/{version}/draft")
def api_update_draft(
    version: str,
    body: DraftPromptUpdate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return update_draft(
        db,
        version,
        prompt_type=body.prompt_type,
        lang=body.lang,
        content_sfw=body.content_sfw,
        content_nsfw=body.content_nsfw,
        doc_content=body.doc_content,
    )


@app.post("/api/versions/{version}/commit")
def api_commit_version(version: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return commit_version(db, version)


@app.post("/api/versions/{version}/translate")
async def api_translate_version(
    version: str,
    body: TranslateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return await translate_draft(
        db,
        version,
        base_url=body.base_url,
        api_key=body.api_key,
        model=body.model,
        temperature=body.temperature,
    )


@app.delete("/api/versions/{version}/draft")
def api_discard_draft(version: str) -> dict[str, Any]:
    return discard_draft(version)


@app.delete("/api/versions/{version}")
def api_delete_version(version: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return delete_version_tree(db, version)


@app.get("/api/jailbreaks")
def api_list_jailbreaks(
    scheme_name: Optional[str] = Query(default=None),
    target_model: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_jailbreaks(db, scheme_name=scheme_name, target_model=target_model)


@app.get("/api/jailbreaks/schemes")
def api_list_jailbreak_schemes(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_jailbreak_schemes(db)


@app.get("/api/jailbreaks/{record_id}")
def api_get_jailbreak(record_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_jailbreak(db, record_id)


@app.post("/api/jailbreaks")
def api_create_jailbreak(
    body: JailbreakCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return create_jailbreak(
        db,
        scheme_name=body.scheme_name,
        target_model=body.target_model,
        content=body.content,
        changelog=body.changelog,
        version=body.version,
        content_mode=body.content_mode,
        modules_json=body.modules_json,
    )


@app.put("/api/jailbreaks/{record_id}")
def api_update_jailbreak(
    record_id: int,
    body: JailbreakUpdateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload = body.model_dump(exclude_unset=True)
    return update_jailbreak(
        db,
        record_id,
        target_model=payload.get("target_model"),
        content=payload.get("content"),
        changelog=payload.get("changelog"),
        content_mode=payload.get("content_mode"),
        modules_json=payload.get("modules_json"),
        modules_json_set="modules_json" in payload,
    )


@app.delete("/api/jailbreaks/{record_id}")
def api_delete_jailbreak(record_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return delete_jailbreak(db, record_id)


@app.post("/api/jailbreaks/{record_id}/next-version")
def api_fork_jailbreak_next_version(
    record_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return fork_next_version(db, record_id)


@app.get("/api/chat-qa-cases")
def api_list_chat_qa_cases(
    user_id: Optional[str] = Query(default=None),
    role_id: Optional[str] = Query(default=None),
    role_name: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_chat_qa_cases(
        db,
        user_id=user_id,
        role_id=role_id,
        role_name=role_name,
    )


@app.get("/api/chat-qa-conversations")
def api_list_chat_qa_conversations(
    user_id: Optional[str] = Query(default=None),
    role_id: Optional[str] = Query(default=None),
    role_name: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_chat_qa_conversations(
        db,
        user_id=user_id,
        role_id=role_id,
        role_name=role_name,
    )


@app.get("/api/chat-qa-conversations/messages")
def api_get_chat_qa_conversation(
    user_id: str = Query(...),
    role_id: str = Query(...),
    app_name: str = Query(default=""),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_chat_qa_conversation(
        db,
        user_id=user_id,
        role_id=role_id,
        app_name=app_name,
    )


@app.get("/api/chat-qa-cases/{record_id}")
def api_get_chat_qa_case(record_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_chat_qa_case(db, record_id)


@app.get("/api/rp-history")
def api_list_rp_history(
    user_id: Optional[str] = Query(default=None),
    role_id: Optional[str] = Query(default=None),
    role_name: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_rp_history(
        db,
        user_id=user_id,
        role_id=role_id,
        role_name=role_name,
    )


@app.get("/api/rp-history/detail")
def api_get_rp_history_detail(
    user_id: str = Query(...),
    role_id: str = Query(...),
    app_name: str = Query(default=""),
    run_group_id: Optional[int] = Query(default=None),
    model: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_rp_history_detail(
        db,
        user_id=user_id,
        role_id=role_id,
        app_name=app_name,
        run_group_id=run_group_id,
        model=model,
    )


@app.get("/api/prompt-test-results")
def api_list_prompt_test_results(
    user_id: Optional[str] = Query(default=None),
    role_id: Optional[str] = Query(default=None),
    role_name: Optional[str] = Query(default=None),
    prompt_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_prompt_test_results(
        db,
        user_id=user_id,
        role_id=role_id,
        role_name=role_name,
        prompt_type=prompt_type,
    )


@app.get("/api/prompt-test-results/by-conversation")
def api_get_prompt_test_result_by_conversation(
    user_id: str = Query(...),
    role_id: str = Query(...),
    app_name: str = Query(default=""),
    prompt_type: str = Query(...),
    model: Optional[str] = Query(default=None),
    run_group_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_prompt_test_result_for_conversation(
        db,
        user_id=user_id,
        role_id=role_id,
        app_name=app_name,
        prompt_type=prompt_type,
        model=model,
        run_group_id=run_group_id,
    )


@app.get("/api/prompt-test-results/{record_id}")
def api_get_prompt_test_result(record_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_prompt_test_result(db, record_id)


@app.post("/api/prompt-test-results")
def api_save_prompt_test_result(
    body: PromptTestResultSaveRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return save_prompt_test_result(db, body)


@app.get("/api/rp-evaluations")
def api_list_rp_evaluations(
    user_id: str = Query(...),
    role_id: str = Query(...),
    app_name: str = Query(default=""),
    run_group_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_rp_evaluations(
        db,
        user_id=user_id,
        role_id=role_id,
        app_name=app_name,
        run_group_id=run_group_id,
    )


@app.get("/api/rp-evaluations/{record_id}")
def api_get_rp_evaluation(record_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_rp_eval(db, record_id)


@app.post("/api/rp-evaluations")
def api_create_rp_evaluation(
    body: RpEvalSaveRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return create_rp_eval(db, body)


@app.delete("/api/rp-evaluations/{record_id}")
def api_delete_rp_evaluation(record_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return delete_rp_eval(db, record_id)


@app.get("/api/brain-analyses")
def api_list_brain_analyses(
    user_id: str = Query(...),
    role_id: str = Query(...),
    app_name: str = Query(default=""),
    run_group_id: Optional[int] = Query(default=None),
) -> list[dict[str, Any]]:
    return list_brain_analyses(
        user_id=user_id,
        role_id=role_id,
        app_name=app_name,
        run_group_id=run_group_id,
    )


@app.get("/api/brain-analyses/{record_id}")
def api_get_brain_analysis(record_id: int) -> dict[str, Any]:
    return get_brain_analysis(record_id)


@app.post("/api/brain-analyses")
def api_create_brain_analysis(body: BrainSaveRequest) -> dict[str, Any]:
    return create_brain_analysis(body)


@app.delete("/api/brain-analyses/{record_id}")
def api_delete_brain_analysis(record_id: int) -> dict[str, Any]:
    return delete_brain_analysis(record_id)


def _build_chat_payload(body: ChatCompletionRequest) -> dict[str, Any]:
    """构造上游 Chat Completions 流式请求体（两个端点共用）。"""
    payload: dict[str, Any] = {
        "model": body.model,
        "messages": [
            {"role": "system", "content": body.system_prompt},
            {"role": "user", "content": body.user_content},
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_completion_tokens": _resolve_max_completion_tokens(body.max_completion_tokens),
        "temperature": body.temperature,
    }
    if body.top_k is not None:
        payload["top_k"] = body.top_k
    if body.extra_body:
        for key, value in body.extra_body.items():
            if value is not None:
                payload[key] = value
    return payload


def _extract_stream_delta(chunk: dict[str, Any]) -> dict[str, Any]:
    """从单个 SSE chunk 提取增量：content / reasoning / finish_reason / usage。"""
    out: dict[str, Any] = {
        "content": "",
        "reasoning": "",
        "finish_reason": None,
        "usage": None,
    }
    usage = chunk.get("usage")
    if isinstance(usage, dict) and usage:
        out["usage"] = usage

    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return out
    choice = choices[0] or {}

    delta = choice.get("delta")
    if isinstance(delta, dict):
        if isinstance(delta.get("content"), str):
            out["content"] = delta["content"]
        if isinstance(delta.get("reasoning_content"), str):
            out["reasoning"] = delta["reasoning_content"]
    else:
        message = choice.get("message")
        if isinstance(message, dict):
            if isinstance(message.get("content"), str):
                out["content"] = message["content"]
            if isinstance(message.get("reasoning_content"), str):
                out["reasoning"] = message["reasoning_content"]

    finish = choice.get("finish_reason")
    if finish:
        out["finish_reason"] = finish
    return out


def _sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _iter_chat_stream(
    base_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    httpx_timeout: "httpx.Timeout",
    request_timeout: float,
):
    """向前端透传归一化 SSE：delta / done / error。"""
    try:
        async with httpx.AsyncClient(timeout=httpx_timeout) as client:
            async with client.stream(
                "POST", base_url, json=payload, headers=headers
            ) as resp:
                if resp.status_code != 200:
                    body_bytes = await resp.aread()
                    yield _sse_event(
                        {
                            "type": "error",
                            "status": resp.status_code,
                            "error": body_bytes.decode("utf-8", "replace")[:2000],
                        }
                    )
                    return

                finish_reason: Optional[str] = None
                usage: dict[str, Any] = {}
                got_content = False
                stream_error: Optional[str] = None

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if not data_str:
                        continue
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except ValueError:
                        continue
                    if isinstance(chunk, dict) and chunk.get("error"):
                        stream_error = json.dumps(chunk["error"], ensure_ascii=False)
                        continue

                    delta = _extract_stream_delta(chunk)
                    if delta["usage"]:
                        usage = delta["usage"]
                    if delta["finish_reason"]:
                        finish_reason = delta["finish_reason"]
                    if delta["content"] or delta["reasoning"]:
                        if delta["content"]:
                            got_content = True
                        yield _sse_event(
                            {
                                "type": "delta",
                                "content": delta["content"],
                                "reasoning": delta["reasoning"],
                            }
                        )

                if stream_error and not got_content:
                    yield _sse_event({"type": "error", "status": 200, "error": stream_error})
                    return

                yield _sse_event(
                    {
                        "type": "done",
                        "finish_reason": finish_reason,
                        "usage": usage,
                    }
                )
    except httpx.TimeoutException as exc:
        yield _sse_event(
            {
                "type": "error",
                "status": 504,
                "error": f"Upstream idle timed out after {int(request_timeout)}s without data: {exc}",
            }
        )
    except httpx.RequestError as exc:
        yield _sse_event({"type": "error", "status": 502, "error": f"Request failed: {exc}"})


@app.post("/api/chat/completions/stream")
async def chat_completions_stream(body: ChatCompletionRequest) -> StreamingResponse:
    base_url = normalize_base_url(body.base_url)
    payload = _build_chat_payload(body)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {body.api_key}",
    }
    request_timeout = _resolve_chat_timeout(body.timeout_seconds)
    httpx_timeout = _stream_httpx_timeout(request_timeout)
    return StreamingResponse(
        _iter_chat_stream(base_url, payload, headers, httpx_timeout, request_timeout),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _accumulate_stream_chunk(chunk: dict[str, Any], acc: dict[str, Any]) -> None:
    """累积一个 SSE chunk 到 acc（content / reasoning / finish_reason / usage）。"""
    usage = chunk.get("usage")
    if isinstance(usage, dict) and usage:
        acc["usage"] = usage

    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return
    choice = choices[0] or {}

    delta = choice.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            acc["content"].append(content)
        reasoning = delta.get("reasoning_content")
        if isinstance(reasoning, str):
            acc["reasoning"].append(reasoning)
    else:
        # 个别网关流式仍返回 message（非增量），兜底取整段
        message = choice.get("message")
        if isinstance(message, dict):
            if isinstance(message.get("content"), str):
                acc["content"].append(message["content"])
            if isinstance(message.get("reasoning_content"), str):
                acc["reasoning"].append(message["reasoning_content"])

    finish = choice.get("finish_reason")
    if finish:
        acc["finish_reason"] = finish


async def _stream_chat_completion(
    base_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    httpx_timeout: "httpx.Timeout",
) -> dict[str, Any]:
    """以流式方式请求上游并累积结果，避免网关读取整段 body 超时。"""
    acc: dict[str, Any] = {
        "content": [],
        "reasoning": [],
        "finish_reason": None,
        "usage": {},
    }
    stream_error: Optional[str] = None
    status_code = 200

    async with httpx.AsyncClient(timeout=httpx_timeout) as client:
        async with client.stream(
            "POST", base_url, json=payload, headers=headers
        ) as resp:
            status_code = resp.status_code
            if resp.status_code != 200:
                body_bytes = await resp.aread()
                return {
                    "status": resp.status_code,
                    "error": body_bytes.decode("utf-8", "replace")[:2000],
                    "raw_text": body_bytes.decode("utf-8", "replace")[:8000],
                }

            async for line in resp.aiter_lines():
                if not line:
                    continue
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if not data_str or data_str == "[DONE]":
                    if data_str == "[DONE]":
                        break
                    continue
                try:
                    chunk = json.loads(data_str)
                except ValueError:
                    continue
                if isinstance(chunk, dict) and chunk.get("error"):
                    stream_error = json.dumps(chunk["error"], ensure_ascii=False)
                    continue
                _accumulate_stream_chunk(chunk, acc)

    raw_content = "".join(acc["content"])
    result: dict[str, Any] = {
        "status": status_code,
        "raw_content": raw_content,
        "reasoning_content": "".join(acc["reasoning"]),
        "finish_reason": acc["finish_reason"],
        "usage": acc["usage"],
        "raw_text": raw_content[:8000],
    }
    if stream_error and not raw_content:
        result["error"] = stream_error
    return result


@app.post("/api/chat/completions")
async def chat_completions(body: ChatCompletionRequest) -> dict[str, Any]:
    base_url = normalize_base_url(body.base_url)
    payload = _build_chat_payload(body)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {body.api_key}",
    }

    request_timeout = _resolve_chat_timeout(body.timeout_seconds)
    httpx_timeout = _stream_httpx_timeout(request_timeout)
    try:
        return await _stream_chat_completion(base_url, payload, headers, httpx_timeout)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=f"Upstream idle timed out after {int(request_timeout)}s without data: {exc}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Request failed: {exc}") from exc
