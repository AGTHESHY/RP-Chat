import type { ChatQaCase, PromptType } from '../api'

export interface SelectedConversation {
  conversation_key: string
  user_id: string
  role_id: string
  app_name: string
  role_name: string
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
) {
  const end = roundEnd ?? getSegmentRoundRange(messages.length).end
  const { start, end: validEnd } = validateRoundRange(roundStart, end, messages.length)
  const slice = messages.slice(start - 1, validEnd)

  return {
    history_messages: [
      {
        role: 'user',
        content: formatConversationRounds(slice, roundStart),
      },
    ],
    old_memory_state: {},
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
  compressExpected: Record<string, unknown>,
  roundStart: number,
  roundEnd: number,
  oldHistoryMemory = '',
) {
  const historySegment = String(compressExpected.history_segment ?? '').trim()
  if (!historySegment) {
    throw new Error('Segment 压缩期望结果缺少 history_segment')
  }

  return {
    old_history_memory: oldHistoryMemory,
    new_history_segments: [
      {
        id: 1,
        start_round: roundStart,
        end_round: roundEnd,
        history_segment: historySegment,
      },
    ],
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
