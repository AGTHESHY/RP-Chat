import type { ChatQaCase, PromptType } from '../api'
import type { HistorySegmentItem } from './memoryPipeline'

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

const DEFAULT_SEGMENT_ROUNDS = 10

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

export function getSegmentRoundRange(messageCount: number): { start: number; end: number } {
  const end = Math.min(DEFAULT_SEGMENT_ROUNDS, messageCount)
  return { start: 1, end: Math.max(end, 1) }
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
  const end = roundEnd ?? getSegmentRoundRange(messages.length).end
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

/** 单段合并的便捷封装，兼容单步测试 */
export function buildHistoryMergePayloadFromSingle(
  compressExpected: Record<string, unknown>,
  roundStart: number,
  roundEnd: number,
  oldHistoryMemory = '',
) {
  const historySegment = String(compressExpected.history_segment ?? '').trim()
  if (!historySegment) {
    throw new Error('Segment 压缩期望结果缺少 history_segment')
  }

  return buildHistoryMergePayload(
    [
      {
        id: 1,
        start_round: roundStart,
        end_round: roundEnd,
        history_segment: historySegment,
      },
    ],
    oldHistoryMemory,
  )
}

export function buildPipelineCompressSaveResult(
  segments: PipelineSegmentSnapshot[],
): Record<string, unknown> {
  if (segments.length === 0) {
    throw new Error('管线压缩结果为空')
  }

  const last = segments[segments.length - 1]
  return {
    history_segment: last.history_segment,
    memory_state: last.memory_state,
    pipeline_segments: segments.map((segment) => ({
      start_round: segment.start_round,
      end_round: segment.end_round,
      history_segment: segment.history_segment,
      memory_state: segment.memory_state,
    })),
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
