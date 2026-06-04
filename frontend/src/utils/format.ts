export function formatConfidence(confidence: number): string {
  if (!Number.isFinite(confidence)) return '—'
  return `${Math.round(confidence * 100)}%`
}

export function formatHistoryTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}
