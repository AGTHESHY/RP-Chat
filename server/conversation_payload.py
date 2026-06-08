"""RP 测试 user payload 构建（与 frontend conversationPayload.ts 对齐）。"""
from __future__ import annotations

import json
from typing import Any

from memory_pipeline import segment_range_for_index


def format_user_line(question: str) -> str:
    text = question.strip()
    if text.startswith('"') or text.startswith("*"):
        return text
    return f'"{text}"'


def format_conversation_rounds(messages: list[dict[str, Any]], round_start: int = 1) -> str:
    parts: list[str] = []
    for index, msg in enumerate(messages):
        round_no = round_start + index
        parts.append(
            f"round {round_no}\n"
            f"用户：{format_user_line(str(msg.get('question', '')))}\n"
            f"助手：{msg.get('answer', '')}"
        )
    return "\n\n".join(parts)


def validate_round_range(round_start: int, round_end: int, message_count: int) -> tuple[int, int]:
    if message_count < 1:
        raise ValueError("该会话没有对话轮次")
    start = int(round_start)
    end = int(round_end)
    if start < 1 or end < 1:
        raise ValueError("测试轮次须为正整数")
    if start > end:
        raise ValueError("起始轮次不能大于结束轮次")
    if end > message_count:
        raise ValueError(f"结束轮次不能超过会话总轮数（共 {message_count} 轮）")
    return start, end


def get_segment_round_range(segment_index: int, message_count: int) -> tuple[int, int]:
    full = segment_range_for_index(segment_index)
    return full["start"], min(full["end"], message_count)


def build_segment_compress_payload(
    messages: list[dict[str, Any]],
    conversation: dict[str, str],
    round_start: int = 1,
    round_end: int | None = None,
    old_memory_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    end = round_end if round_end is not None else get_segment_round_range(1, len(messages))[1]
    start, valid_end = validate_round_range(round_start, end, len(messages))
    slice_msgs = messages[start - 1 : valid_end]

    user_id = conversation["user_id"]
    role_id = conversation["role_id"]
    try:
        user_num = int(user_id)
    except ValueError:
        user_num = user_id
    try:
        bot_num = int(role_id)
    except ValueError:
        bot_num = role_id

    return {
        "history_messages": [
            {
                "role": "user",
                "content": format_conversation_rounds(slice_msgs, start),
            }
        ],
        "old_memory_state": old_memory_state or {},
        "scope": {
            "user_id": user_num,
            "bot_id": bot_num,
            "scenario_id": 0,
            "group_id": 0,
        },
        "round_range": {
            "start_round": start,
            "end_round": valid_end,
        },
    }


def build_history_merge_payload(
    segments: list[dict[str, Any]],
    old_history_memory: str = "",
) -> dict[str, Any]:
    if not segments:
        raise ValueError("History 合并至少需要一个 history_segment")

    normalized: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        history_segment = str(segment.get("history_segment", "")).strip()
        if not history_segment:
            raise ValueError(f"Segment 压缩期望结果缺少 history_segment（第 {index + 1} 段）")
        normalized.append(
            {
                "id": segment.get("id", index + 1),
                "start_round": segment["start_round"],
                "end_round": segment["end_round"],
                "history_segment": history_segment,
            }
        )

    return {
        "old_history_memory": old_history_memory,
        "new_history_segments": normalized,
    }


def pick_consecutive_segments(
    segments: list[dict[str, Any]],
    count: int,
    end_index: int,
) -> list[dict[str, Any]]:
    if not segments:
        raise ValueError("没有可用的压缩段")
    if count < 1 or count > 4:
        raise ValueError("合并段数须在 1-4 之间")
    if end_index < 1 or end_index > len(segments):
        raise ValueError(f"截至段须在 1-{len(segments)} 之间")
    if end_index - count + 1 < 1:
        raise ValueError(f"截至第 {end_index} 段时，最多只能向前连续合并 {end_index} 段")

    start_index = end_index - count
    result: list[dict[str, Any]] = []
    for offset, segment in enumerate(segments[start_index:end_index]):
        result.append(
            {
                "id": start_index + offset + 1,
                "start_round": segment["start_round"],
                "end_round": segment["end_round"],
                "history_segment": segment["history_segment"],
            }
        )
    return result


def segment_range_key(start: int, end: int) -> str:
    return f"{start}-{end}"


def strip_markdown_fence(text: str) -> str:
    clean = text.strip()
    if clean.startswith("```"):
        first_newline = clean.find("\n")
        if first_newline != -1:
            clean = clean[first_newline + 1 :]
        if clean.endswith("```"):
            clean = clean[:-3]
    return clean.strip()


def parse_model_json(raw: str) -> dict[str, Any] | None:
    if not raw.strip():
        return None
    try:
        return json.loads(strip_markdown_fence(raw))
    except json.JSONDecodeError:
        return None
