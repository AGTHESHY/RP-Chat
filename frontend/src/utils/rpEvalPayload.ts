import type { ChatQaCase, RpHistoryDetail, RpHistoryRunMeta } from '../api'
import { formatConversationRounds } from './conversationPayload'

export interface BuildRpEvalPayloadInput {
  messages: ChatQaCase[]
  detail: RpHistoryDetail
}

export function buildRpEvalUserContent(input: BuildRpEvalPayloadInput): string {
  const { messages, detail } = input
  const slice = messages.slice(detail.round_start - 1, detail.round_end)
  const sourceDialogue = formatConversationRounds(slice, detail.round_start)

  const payload = {
    meta: {
      user_id: detail.user_id,
      role_id: detail.role_id,
      app_name: detail.app_name,
      role_name: detail.role_name,
      round_start: detail.round_start,
      round_end: detail.round_end,
      conversation_key: detail.conversation_key,
    },
    source_dialogue: sourceDialogue,
    segment_compress: detail.compress,
    history_merge: detail.merge,
    run_meta: {
      compress: formatRunMeta(detail.compress_run),
      merge: formatRunMeta(detail.merge_run),
      compress_updated_at: detail.compress_updated_at,
      merge_updated_at: detail.merge_updated_at,
    },
  }

  return JSON.stringify(payload, null, 2)
}

function formatRunMeta(run: RpHistoryRunMeta | null): Record<string, unknown> | null {
  if (!run) return null
  return {
    prompt_version: run.prompt_version,
    model: run.model,
    top_k: run.top_k,
    temperature: run.temperature,
    updated_at: run.updated_at,
  }
}
