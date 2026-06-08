export const FIRST_SEGMENT_ROUNDS = 10
export const BATCH_MERGE_SIZE = 4

/** 滑动段：第 1 段 1-10；第 n≥2 段为 10*(n-1)+1 ～ 10*n+1 */
export function segmentRangeForIndex(segmentIndex: number): SegmentRange {
  if (segmentIndex < 1) {
    throw new Error('segment_index must be >= 1')
  }
  if (segmentIndex === 1) {
    return { start: 1, end: 10 }
  }
  return {
    start: 10 * (segmentIndex - 1) + 1,
    end: 10 * segmentIndex + 1,
  }
}

export function maxSegmentIndexForRounds(messageCount: number): number {
  if (messageCount < 1) return 0
  let index = 1
  while (segmentRangeForIndex(index).start <= messageCount) {
    index += 1
  }
  return Math.max(index - 1, 0)
}

export interface SegmentRange {
  start: number
  end: number
}

export interface HistorySegmentItem {
  id: number
  start_round: number
  end_round: number
  history_segment: string
}

export type PipelineMergeMode = 'single' | 'batch' | 'forced_tail'

export interface PipelineCompressStep {
  type: 'compress'
  segment: SegmentRange
  segmentIndex: number
}

export interface PipelineMergeStep {
  type: 'merge'
  segments: SegmentRange[]
  mergeMode: PipelineMergeMode
}

export type PipelineStep = PipelineCompressStep | PipelineMergeStep

export interface PipelinePlan {
  rangeStart: number
  rangeEnd: number
  segments: SegmentRange[]
  steps: PipelineStep[]
  compressCount: number
  mergeCount: number
  hasForcedTailMerge: boolean
}

/** 按滑动段公式切分，与用户选定范围取交集 */
export function splitGlobalSegments(rangeStart: number, rangeEnd: number): SegmentRange[] {
  const start = Math.floor(rangeStart)
  const end = Math.floor(rangeEnd)
  if (start > end) return []

  const segments: SegmentRange[] = []
  let index = 1
  while (true) {
    const full = segmentRangeForIndex(index)
    if (full.start > end) break
    if (full.end >= start) {
      const segStart = full.start
      const segEnd = Math.min(full.end, end)
      if (segStart <= segEnd) {
        segments.push({ start: segStart, end: segEnd })
      }
    }
    index += 1
  }

  return segments
}

function segmentRangeLabel(segments: SegmentRange[]): string {
  if (segments.length === 0) return ''
  if (segments.length === 1) {
    const seg = segments[0]
    return `${seg.start}-${seg.end}轮`
  }
  const first = segments[0]
  const last = segments[segments.length - 1]
  return `${first.start}-${last.end}轮（${segments.length}段）`
}

function pushMergeStep(
  steps: PipelineStep[],
  segments: SegmentRange[],
  mergeMode: PipelineMergeMode,
): void {
  if (segments.length === 0) return
  steps.push({
    type: 'merge',
    segments: segments.map((seg) => ({ ...seg })),
    mergeMode,
  })
}

/**
 * 链路测试合并策略：始终每攒满 4 段批量合并；末尾不足 4 段时 forced_tail。
 * 单段合并仅用于单步测试，不在链路测试中生成。
 */
export function planMemoryPipeline(rangeStart: number, rangeEnd: number): PipelinePlan {
  const segments = splitGlobalSegments(rangeStart, rangeEnd)
  const steps: PipelineStep[] = []
  let pendingBatch: SegmentRange[] = []
  let hasForcedTailMerge = false

  segments.forEach((segment, index) => {
    steps.push({
      type: 'compress',
      segment: { ...segment },
      segmentIndex: index + 1,
    })

    pendingBatch.push({ ...segment })
    if (pendingBatch.length >= BATCH_MERGE_SIZE) {
      pushMergeStep(steps, pendingBatch, 'batch')
      pendingBatch = []
    }
  })

  if (pendingBatch.length > 0) {
    hasForcedTailMerge = pendingBatch.length < BATCH_MERGE_SIZE
    pushMergeStep(steps, pendingBatch, hasForcedTailMerge ? 'forced_tail' : 'batch')
    pendingBatch = []
  }

  return {
    rangeStart,
    rangeEnd,
    segments,
    steps,
    compressCount: segments.length,
    mergeCount: steps.filter((step) => step.type === 'merge').length,
    hasForcedTailMerge,
  }
}

export function pipelinePlanSummary(plan: PipelinePlan): string {
  const parts = [`${plan.compressCount} 段压缩`, `${plan.mergeCount} 次合并`]
  if (plan.hasForcedTailMerge) {
    parts.push('含 1 次强制尾批')
  }
  return parts.join(' + ')
}

export function pipelineStepLabel(step: PipelineStep): string {
  if (step.type === 'compress') {
    const { start, end } = step.segment
    return `Segment 压缩 · 第 ${start}-${end} 轮（段 ${step.segmentIndex}）`
  }

  const label = segmentRangeLabel(step.segments)
  if (step.mergeMode === 'single') {
    return `History 合并 · 单段 · ${label}`
  }
  if (step.mergeMode === 'batch') {
    return `History 合并 · 批量 ${step.segments.length} 段 · ${label}`
  }
  return `History 合并 · 强制尾批 ${step.segments.length} 段 · ${label}`
}

function roundRangeText(start: number, end: number): string {
  return start === end ? `第 ${start} 轮` : `第 ${start}-${end} 轮`
}

/** 将相邻的 compress + merge 合并为一句，用于管线预览 */
export function formatPipelineCycleLines(plan: PipelinePlan): string[] {
  const lines: string[] = []
  let index = 0

  while (index < plan.steps.length) {
    const step = plan.steps[index]
    if (step.type !== 'compress') {
      index += 1
      continue
    }

    const compressSteps: PipelineCompressStep[] = [step]
    let cursor = index + 1
    while (cursor < plan.steps.length && plan.steps[cursor].type === 'compress') {
      compressSteps.push(plan.steps[cursor] as PipelineCompressStep)
      cursor += 1
    }

    const mergeStep = plan.steps[cursor]
    if (mergeStep?.type === 'merge') {
      const first = compressSteps[0].segment
      const last = compressSteps[compressSteps.length - 1].segment
      const batchRoundLabel = roundRangeText(first.start, last.end)
      if (mergeStep.mergeMode === 'forced_tail') {
        lines.push(
          `${batchRoundLabel}：${compressSteps.length} 段 Segment 压缩后强制合并（尾批不足 4 段）`,
        )
      } else {
        lines.push(`${batchRoundLabel}：${compressSteps.length} 段 Segment 压缩后批量合并`)
      }
      index = cursor + 1
      continue
    }

    lines.push(`${roundRangeText(step.segment.start, step.segment.end)}：Segment 压缩`)
    index += 1
  }

  return lines
}
