import type { RpEvalSummary } from '../api'

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
