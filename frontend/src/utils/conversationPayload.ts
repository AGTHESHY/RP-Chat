import type { ChatQaCase, PromptType, RpCompressSegmentDetail } from '../api'
import type { HistorySegmentItem } from './memoryPipeline'
import { segmentRangeForIndex } from './memoryPipeline'

export interface SelectedConversation {
  conversation_key: string
  user_id: string
  role_id: string
  app_name: string
  role_name: string
}

export interface PipelineSegmentSnapshot {
  start_round: number
  end_round: number
  history_segment: string
  memory_state: Record<string, unknown>
}

export interface MergeableSegment {
  index: number
  start_round: number
  end_round: number
  history_segment: string
}

export interface CompressResultMeta {
  round_start: number
  round_end: number
}

export { segmentRangeForIndex } from './memoryPipeline'

export function maxNextSegmentIndex(
  existingIndexes: number[],
  messageCount: number,
): number | null {
  const maxExisting = existingIndexes.length > 0 ? Math.max(...existingIndexes) : 0
  const next = maxExisting + 1
  const range = segmentRangeForIndex(next)
  if (range.start > messageCount) return null
  return next
}

function formatUserLine(question: string): string {
  const text = question.trim()
  if (text.startsWith('"') || text.startsWith('*')) {
    return text
  }
  return `"${text}"`
}

export function formatConversationRounds(
  messages: ChatQaCase[],
  roundStart = 1,
): string {
  return messages
    .map((msg, index) => {
      const round = roundStart + index
      return `round ${round}\n用户：${formatUserLine(msg.question)}\n助手：${msg.answer}`
    })
    .join('\n\n')
}

export function getSegmentRoundRange(
  segmentIndex: number,
  messageCount: number,
): { start: number; end: number } {
  const range = segmentRangeForIndex(segmentIndex)
  return {
    start: range.start,
    end: Math.min(range.end, messageCount),
  }
}

export function validateRoundRange(
  roundStart: number,
  roundEnd: number,
  messageCount: number,
): { start: number; end: number } {
  if (messageCount < 1) {
    throw new Error('该会话没有对话轮次')
  }
  const start = Math.floor(roundStart)
  const end = Math.floor(roundEnd)
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 1 || end < 1) {
    throw new Error('测试轮次须为正整数')
  }
  if (start > end) {
    throw new Error('起始轮次不能大于结束轮次')
  }
  if (end > messageCount) {
    throw new Error(`结束轮次不能超过会话总轮数（共 ${messageCount} 轮）`)
  }
  return { start, end }
}

export function buildSegmentCompressPayload(
  messages: ChatQaCase[],
  conversation: SelectedConversation,
  roundStart = 1,
  roundEnd?: number,
  oldMemoryState: Record<string, unknown> = {},
) {
  const end = roundEnd ?? getSegmentRoundRange(1, messages.length).end
  const { start, end: validEnd } = validateRoundRange(roundStart, end, messages.length)
  const slice = messages.slice(start - 1, validEnd)

  return {
    history_messages: [
      {
        role: 'user',
        content: formatConversationRounds(slice, start),
      },
    ],
    old_memory_state: oldMemoryState,
    scope: {
      user_id: Number(conversation.user_id) || conversation.user_id,
      bot_id: Number(conversation.role_id) || conversation.role_id,
      scenario_id: 0,
      group_id: 0,
    },
    round_range: {
      start_round: start,
      end_round: validEnd,
    },
  }
}

export function buildHistoryMergePayload(
  segments: HistorySegmentItem[],
  oldHistoryMemory = '',
) {
  if (segments.length === 0) {
    throw new Error('History 合并至少需要一个 history_segment')
  }

  const normalized = segments.map((segment, index) => {
    const historySegment = String(segment.history_segment ?? '').trim()
    if (!historySegment) {
      throw new Error(`Segment 压缩期望结果缺少 history_segment（第 ${index + 1} 段）`)
    }
    return {
      id: segment.id ?? index + 1,
      start_round: segment.start_round,
      end_round: segment.end_round,
      history_segment: historySegment,
    }
  })

  return {
    old_history_memory: oldHistoryMemory,
    new_history_segments: normalized,
  }
}

export function mergeableSegmentsFromRecords(
  records: RpCompressSegmentDetail[],
): MergeableSegment[] {
  return [...records]
    .sort((a, b) => a.segment_index - b.segment_index)
    .map((row) => {
      const historySegment = String(row.expected_result.history_segment ?? '').trim()
      if (!historySegment) {
        throw new Error(`段 ${row.segment_index} 缺少 history_segment`)
      }
      return {
        index: row.segment_index,
        start_round: row.round_start,
        end_round: row.round_end,
        history_segment: historySegment,
      }
    })
}

export function extractMergeableSegments(
  compress: Record<string, unknown>,
  fallback?: CompressResultMeta,
): MergeableSegment[] {
  const pipelineSegments = compress.pipeline_segments
  if (Array.isArray(pipelineSegments) && pipelineSegments.length > 0) {
    return pipelineSegments.map((item, index) => {
      const row = item as Record<string, unknown>
      const historySegment = String(row.history_segment ?? '').trim()
      if (!historySegment) {
        throw new Error(`pipeline_segments 第 ${index + 1} 段缺少 history_segment`)
      }
      const startRound = Number(row.start_round)
      const endRound = Number(row.end_round)
      if (!Number.isFinite(startRound) || !Number.isFinite(endRound) || startRound < 1 || endRound < startRound) {
        throw new Error(`pipeline_segments 第 ${index + 1} 段轮次无效`)
      }
      return {
        index: index + 1,
        start_round: startRound,
        end_round: endRound,
        history_segment: historySegment,
      }
    })
  }

  const historySegment = String(compress.history_segment ?? '').trim()
  if (!historySegment) {
    throw new Error('Segment 压缩期望结果缺少 history_segment')
  }
  if (!fallback) {
    throw new Error('单段压缩结果缺少轮次元数据')
  }

  return [
    {
      index: 1,
      start_round: fallback.round_start,
      end_round: fallback.round_end,
      history_segment: historySegment,
    },
  ]
}

export function pickConsecutiveSegments(
  segments: MergeableSegment[],
  count: number,
  endIndex: number,
): HistorySegmentItem[] {
  if (segments.length === 0) {
    throw new Error('没有可用的压缩段')
  }
  if (!Number.isInteger(count) || count < 1 || count > 4) {
    throw new Error('合并段数须在 1-4 之间')
  }
  if (!Number.isInteger(endIndex) || endIndex < 1 || endIndex > segments.length) {
    throw new Error(`截至段须在 1-${segments.length} 之间`)
  }
  if (endIndex - count + 1 < 1) {
    throw new Error(`截至第 ${endIndex} 段时，最多只能向前连续合并 ${endIndex} 段`)
  }

  const startIndex = endIndex - count
  return segments.slice(startIndex, endIndex).map((segment, offset) => ({
    id: startIndex + offset + 1,
    start_round: segment.start_round,
    end_round: segment.end_round,
    history_segment: segment.history_segment,
  }))
}

export function mergeRoundRangeFromSegments(
  segments: Array<Pick<HistorySegmentItem, 'start_round' | 'end_round'>>,
): { start: number; end: number } {
  if (segments.length === 0) {
    throw new Error('合并段为空')
  }
  return {
    start: Math.min(...segments.map((segment) => segment.start_round)),
    end: Math.max(...segments.map((segment) => segment.end_round)),
  }
}

export function stripMarkdownFence(text: string): string {
  let clean = text.trim()
  if (!clean.startsWith('```')) {
    return clean
  }
  const firstNewline = clean.indexOf('\n')
  if (firstNewline !== -1) {
    clean = clean.slice(firstNewline + 1)
  }
  if (clean.endsWith('```')) {
    clean = clean.slice(0, -3)
  }
  return clean.trim()
}

export function parseModelJson(content: string): Record<string, unknown> | null {
  if (!content.trim()) return null
  try {
    return JSON.parse(stripMarkdownFence(content)) as Record<string, unknown>
  } catch {
    return null
  }
}

export function promptTypeLabel(type: PromptType): string {
  return type === 'segment_compress' ? 'Segment 压缩' : 'History 合并'
}
