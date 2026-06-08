"""上游 Chat Completions 非流式累积调用。"""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from version_service import normalize_base_url


def stream_httpx_timeout() -> httpx.Timeout:
    return httpx.Timeout(connect=30.0, read=None, write=60.0, pool=30.0)


def resolve_max_completion_tokens(max_completion_tokens: Optional[int]) -> int:
    if max_completion_tokens is None:
        return 4096
    return max(1024, min(16384, int(max_completion_tokens)))


def build_chat_payload(
    *,
    model: str,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.3,
    top_k: Optional[int] = None,
    max_completion_tokens: Optional[int] = None,
    extra_body: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_completion_tokens": resolve_max_completion_tokens(max_completion_tokens),
        "temperature": temperature,
    }
    if top_k is not None:
        payload["top_k"] = top_k
    if extra_body:
        for key, value in extra_body.items():
            if value is not None:
                payload[key] = value
    return payload


def _accumulate_stream_chunk(chunk: dict[str, Any], acc: dict[str, Any]) -> None:
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
        message = choice.get("message")
        if isinstance(message, dict):
            if isinstance(message.get("content"), str):
                acc["content"].append(message["content"])
            if isinstance(message.get("reasoning_content"), str):
                acc["reasoning"].append(message["reasoning_content"])

    finish = choice.get("finish_reason")
    if finish:
        acc["finish_reason"] = finish


async def stream_chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.3,
    top_k: Optional[int] = None,
    max_completion_tokens: Optional[int] = None,
    extra_body: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    normalized_url = normalize_base_url(base_url)
    payload = build_chat_payload(
        model=model,
        system_prompt=system_prompt,
        user_content=user_content,
        temperature=temperature,
        top_k=top_k,
        max_completion_tokens=max_completion_tokens,
        extra_body=extra_body,
    )
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    httpx_timeout = stream_httpx_timeout()

    acc: dict[str, Any] = {
        "content": [],
        "reasoning": [],
        "finish_reason": None,
        "usage": {},
    }
    stream_error: Optional[str] = None
    status_code = 200

    async with httpx.AsyncClient(timeout=httpx_timeout) as client:
        async with client.stream("POST", normalized_url, json=payload, headers=headers) as resp:
            status_code = resp.status_code
            if resp.status_code != 200:
                body_bytes = await resp.aread()
                return {
                    "status": resp.status_code,
                    "error": body_bytes.decode("utf-8", "replace")[:2000],
                    "raw_text": body_bytes.decode("utf-8", "replace")[:8000],
                    "raw_content": "",
                    "reasoning_content": "",
                    "finish_reason": None,
                    "usage": {},
                }

            async for line in resp.aiter_lines():
                if not line:
                    continue
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:") :].strip()
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
