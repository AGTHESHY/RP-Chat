import type { BrainAnalysisSummary, RpEvalSummary, RpHistoryDetail } from '../api'

function sortedModels(models: string[]): string[] {
  return [...models].map((m) => m.trim()).filter(Boolean).sort((a, b) => a.localeCompare(b))
}

/** 当前 RP 测试任务参与测评的模型集合 */
export function taskModelSetFromDetail(detail: RpHistoryDetail): string[] {
  return sortedModels(
    detail.model_runs.filter((run) => run.compress || run.merge).map((run) => run.model),
  )
}

function taskCompressVersion(detail: RpHistoryDetail): string {
  const run = detail.model_runs.find((r) => r.compress_run?.prompt_version)
  return run?.compress_run?.prompt_version ?? detail.prompt_version ?? ''
}

function taskMergeVersion(detail: RpHistoryDetail): string {
  const run = detail.model_runs.find((r) => r.merge_run?.prompt_version)
  return run?.merge_run?.prompt_version ?? ''
}

function sameConversation(
  row: { user_id: string; role_id: string; app_name: string },
  detail: RpHistoryDetail,
): boolean {
  return (
    row.user_id === detail.user_id &&
    row.role_id === detail.role_id &&
    row.app_name === detail.app_name
  )
}

/** 无 run_group_id 的旧记录：按轮次 + SP 版本 + 被测模型集合匹配 */
function legacyEvalFingerprintMatch(row: RpEvalSummary, detail: RpHistoryDetail): boolean {
  if (row.round_start !== detail.round_start || row.round_end !== detail.round_end) {
    return false
  }

  const taskHasCompress = detail.model_runs.some((r) => r.compress)
  const taskHasMerge = detail.model_runs.some((r) => r.merge)
  if (row.has_compress !== taskHasCompress || row.has_merge !== taskHasMerge) {
    return false
  }

  const cVer = taskCompressVersion(detail)
  const mVer = taskMergeVersion(detail)
  if (row.has_compress && cVer && row.compress_prompt_version !== cVer) return false
  if (row.has_merge && mVer && row.merge_prompt_version !== mVer) return false

  const taskModels = taskModelSetFromDetail(detail)
  const rowModels = sortedModels(row.evaluated_models ?? [])
  if (rowModels.length === 0) {
    if (taskModels.length === 1 && row.model && row.model === taskModels[0]) {
      return true
    }
    return false
  }
  if (taskModels.length !== rowModels.length) return false
  return taskModels.every((model, index) => model === rowModels[index])
}

export function evalMatchesRpTask(row: RpEvalSummary, detail: RpHistoryDetail): boolean {
  if (!sameConversation(row, detail)) return false
  const runGroupId = row.run_group_id ?? 0
  if (runGroupId > 0) {
    return runGroupId === detail.run_group_id
  }
  return legacyEvalFingerprintMatch(row, detail)
}

export function filterEvaluationsForTask(
  rows: RpEvalSummary[],
  detail: RpHistoryDetail,
): RpEvalSummary[] {
  return rows.filter((row) => evalMatchesRpTask(row, detail))
}

function legacyBrainFingerprintMatch(row: BrainAnalysisSummary, detail: RpHistoryDetail): boolean {
  if (row.round_start !== detail.round_start || row.round_end !== detail.round_end) {
    return false
  }

  const cVer = taskCompressVersion(detail)
  const mVer = taskMergeVersion(detail)
  if (cVer && row.compress_prompt_version !== cVer) return false
  if (mVer && row.merge_prompt_version !== mVer) return false

  const taskModels = taskModelSetFromDetail(detail)
  const rowModels = sortedModels(row.evaluated_models ?? [])
  if (rowModels.length === 0) {
    return taskModels.length === 1 && Boolean(row.model) && row.model === taskModels[0]
  }
  if (taskModels.length !== rowModels.length) return false
  return taskModels.every((model, index) => model === rowModels[index])
}

export function brainMatchesRpTask(
  row: BrainAnalysisSummary,
  detail: RpHistoryDetail,
  taskEvalIds: ReadonlySet<number>,
): boolean {
  if (!sameConversation(row, detail)) return false
  const runGroupId = row.run_group_id ?? 0
  if (runGroupId > 0) {
    return runGroupId === detail.run_group_id
  }
  if (taskEvalIds.has(row.rp_eval_id)) return true
  return legacyBrainFingerprintMatch(row, detail)
}

export function filterBrainAnalysesForTask(
  rows: BrainAnalysisSummary[],
  detail: RpHistoryDetail,
  taskEvalIds: ReadonlySet<number>,
): BrainAnalysisSummary[] {
  return rows.filter((row) => brainMatchesRpTask(row, detail, taskEvalIds))
}
