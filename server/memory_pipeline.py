"""RP 链路测试分段与合并计划（与 frontend memoryPipeline.ts 对齐）。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, TypedDict, Union

FIRST_SEGMENT_ROUNDS = 10
BATCH_MERGE_SIZE = 4

PipelineMergeMode = Literal["single", "batch", "forced_tail"]


class SegmentRange(TypedDict):
    start: int
    end: int


class PipelineCompressStep(TypedDict):
    type: Literal["compress"]
    segment: SegmentRange
    segmentIndex: int


class PipelineMergeStep(TypedDict):
    type: Literal["merge"]
    segments: list[SegmentRange]
    mergeMode: PipelineMergeMode


PipelineStep = Union[PipelineCompressStep, PipelineMergeStep]


class PipelinePlan(TypedDict):
    rangeStart: int
    rangeEnd: int
    segments: list[SegmentRange]
    steps: list[PipelineStep]
    compressCount: int
    mergeCount: int
    hasForcedTailMerge: bool


def segment_range_for_index(segment_index: int) -> SegmentRange:
    if segment_index < 1:
        raise ValueError("segment_index must be >= 1")
    return {
        "start": (segment_index - 1) * FIRST_SEGMENT_ROUNDS + 1,
        "end": segment_index * FIRST_SEGMENT_ROUNDS,
    }


def split_global_segments(range_start: int, range_end: int) -> list[SegmentRange]:
    start = int(range_start)
    end = int(range_end)
    if start > end:
        return []

    segments: list[SegmentRange] = []
    index = 1
    while True:
        full = segment_range_for_index(index)
        if full["start"] > end:
            break
        if full["end"] >= start:
            seg_start = full["start"]
            seg_end = min(full["end"], end)
            if seg_start <= seg_end:
                segments.append({"start": seg_start, "end": seg_end})
        index += 1
    return segments


def _push_merge_step(
    steps: list[PipelineStep],
    segments: list[SegmentRange],
    merge_mode: PipelineMergeMode,
) -> None:
    if not segments:
        return
    steps.append(
        {
            "type": "merge",
            "segments": [deepcopy(seg) for seg in segments],
            "mergeMode": merge_mode,
        }
    )


def plan_memory_pipeline(range_start: int, range_end: int) -> PipelinePlan:
    segments = split_global_segments(range_start, range_end)
    steps: list[PipelineStep] = []
    pending_batch: list[SegmentRange] = []
    has_forced_tail_merge = False

    for index, segment in enumerate(segments):
        steps.append(
            {
                "type": "compress",
                "segment": deepcopy(segment),
                "segmentIndex": index + 1,
            }
        )
        pending_batch.append(deepcopy(segment))
        if len(pending_batch) >= BATCH_MERGE_SIZE:
            _push_merge_step(steps, pending_batch, "batch")
            pending_batch = []

    if pending_batch:
        has_forced_tail_merge = len(pending_batch) < BATCH_MERGE_SIZE
        _push_merge_step(
            steps,
            pending_batch,
            "forced_tail" if has_forced_tail_merge else "batch",
        )

    return {
        "rangeStart": range_start,
        "rangeEnd": range_end,
        "segments": segments,
        "steps": steps,
        "compressCount": len(segments),
        "mergeCount": sum(1 for step in steps if step["type"] == "merge"),
        "hasForcedTailMerge": has_forced_tail_merge,
    }


def pipeline_step_label(step: PipelineStep) -> str:
    if step["type"] == "compress":
        seg = step["segment"]
        return f"Segment 压缩 · 第 {seg['start']}-{seg['end']} 轮（段 {step['segmentIndex']}）"

    segments = step["segments"]
    if len(segments) == 1:
        label = f"{segments[0]['start']}-{segments[0]['end']}轮"
    else:
        label = f"{segments[0]['start']}-{segments[-1]['end']}轮（{len(segments)}段）"

    mode = step["mergeMode"]
    if mode == "single":
        return f"History 合并 · 单段 · {label}"
    if mode == "batch":
        return f"History 合并 · 批量 {len(segments)} 段 · {label}"
    return f"History 合并 · 强制尾批 {len(segments)} 段 · {label}"
