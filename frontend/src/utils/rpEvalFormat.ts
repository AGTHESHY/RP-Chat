import type {
  BrainAnalysisSummary,
  RpEvalSummary,
  RpHistoryDetail,
  RpHistorySummary,
} from '../api'
import { formatHistoryTime } from './format'

/** 与「RP测试历史」表格行数一致；无产出时显示 — */
export function formatRpHistoryModelCount(
  row: RpHistorySummary,
  selectedHistoryKey: string,
  detail: RpHistoryDetail | null,
): string {
  if (
    detail &&
    row.history_key === selectedHistoryKey &&
    detail.run_group_id === row.run_group_id
  ) {
    const n = detail.model_runs.length
    return n > 0 ? String(n) : '—'
  }
  if (!row.has_compress && !row.has_merge) return '—'
  return row.model_count > 0 ? String(row.model_count) : '—'
}

export function formatEvaluatedModels(row: RpEvalSummary): string {
  const models = Array.isArray(row.evaluated_models) ? row.evaluated_models : []
  if (models.length === 0) return '—'
  if (row.eval_mode === 'multi_compare' || models.length > 1) {
    return `${models.length}模型`
  }
  return models[0]
}

/** 测评历史列表行的可读摘要，用于智脑「关联测评」等场景 */
export function formatEvalHistoryLabel(row: RpEvalSummary): string {
  const parts = [
    formatHistoryTime(row.created_at),
    formatEvalPromptVersions(row),
    formatEvaluatedModels(row),
    `${row.overall_score}分`,
  ].filter((part) => part && part !== '—')
  const summary = parts.join(' · ')
  return summary ? `${summary}（#${row.id}）` : `#${row.id}`
}

export function formatEvalPromptVersions(row: RpEvalSummary): string {
  const parts: string[] = []
  if (row.has_compress && row.compress_prompt_version) {
    parts.push(`C:${row.compress_prompt_version}`)
  }
  if (row.has_merge && row.merge_prompt_version) {
    parts.push(`M:${row.merge_prompt_version}`)
  }
  return parts.join(' ') || '—'
}

export function formatBrainPromptVersions(row: BrainAnalysisSummary): string {
  const parts: string[] = []
  if (row.compress_prompt_version) {
    parts.push(`C:${row.compress_prompt_version}`)
  }
  if (row.merge_prompt_version) {
    parts.push(`M:${row.merge_prompt_version}`)
  }
  return parts.join(' ') || '—'
}
