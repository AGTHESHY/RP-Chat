/** Build query string from optional string fields (skips empty). */
export function buildQuery(
  params: Record<string, string | number | boolean | null | undefined>,
): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    const s = String(value).trim()
    if (!s) continue
    search.set(key, s)
  }
  const q = search.toString()
  return q ? `?${q}` : ''
}
