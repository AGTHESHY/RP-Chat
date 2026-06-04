import type { ChatQaCase, RpHistoryDetail, RpHistoryModelRun, RpHistoryRunMeta } from '../api'
import { formatConversationRounds } from './conversationPayload'

export interface BuildRpEvalPayloadInput {
  messages: ChatQaCase[]
  detail: RpHistoryDetail
  /** 单模型时长度 1；多模型对比时传入多个 run */
  modelRuns: RpHistoryModelRun[]
}

export function buildRpEvalUserContent(input: BuildRpEvalPayloadInput): string {
  const { messages, detail, modelRuns } = input
  const slice = messages.slice(detail.round_start - 1, detail.round_end)
  const sourceDialogue = formatConversationRounds(slice, detail.round_start)

  const meta = {
    user_id: detail.user_id,
    role_id: detail.role_id,
    app_name: detail.app_name,
    role_name: detail.role_name,
    round_start: detail.round_start,
    round_end: detail.round_end,
    conversation_key: detail.conversation_key,
    prompt_version: detail.prompt_version,
  }

  if (modelRuns.length <= 1) {
    const run = modelRuns[0]
    const payload = {
      meta,
      source_dialogue: sourceDialogue,
      segment_compress: run?.compress ?? null,
      history_merge: run?.merge ?? null,
      run_meta: {
        model: run?.model ?? '',
        compress: formatRunMeta(run?.compress_run ?? null),
        merge: formatRunMeta(run?.merge_run ?? null),
        compress_updated_at: run?.compress_run?.updated_at ?? null,
        merge_updated_at: run?.merge_run?.updated_at ?? null,
      },
    }
    return JSON.stringify(payload, null, 2)
  }

  const payload = {
    meta,
    source_dialogue: sourceDialogue,
    comparison_mode: true,
    model_outputs: modelRuns.map((run) => ({
      model: run.model,
      segment_compress: run.compress,
      history_merge: run.merge,
      run_meta: {
        compress: formatRunMeta(run.compress_run),
        merge: formatRunMeta(run.merge_run),
        compress_updated_at: run.compress_run?.updated_at ?? null,
        merge_updated_at: run.merge_run?.updated_at ?? null,
      },
    })),
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

/** 从 RP 历史详情中取出可用于测评的模型 run */
export function pickEvaluableModelRuns(
  detail: RpHistoryDetail,
  models: string[],
): RpHistoryModelRun[] {
  const set = new Set(models)
  return detail.model_runs.filter(
    (run) => set.has(run.model) && Boolean(run.compress || run.merge),
  )
}
