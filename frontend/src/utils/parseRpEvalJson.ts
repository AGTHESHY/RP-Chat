export interface RpEvalDimension {
  id: string
  name: string
  score: number
  confidence: number
  evidence: string
  issues: string[]
}

export interface RpEvalModuleResult {
  available: boolean
  subscore: number
  confidence: number
  dimensions: RpEvalDimension[]
}

export interface RpEvalCrossConsistency {
  available: boolean
  score: number
  confidence: number
  notes: string
}

export interface RpEvalParsed {
  overall_score: number
  overall_confidence: number
  summary: string
  segment_compress: RpEvalModuleResult
  history_merge: RpEvalModuleResult
  cross_consistency: RpEvalCrossConsistency
  recommendations: string[]
}

export interface ParseRpEvalResult {
  ok: boolean
  error?: string
  data?: RpEvalParsed
}

export function stripMarkdownFence(text: string): string {
  let clean = text.trim()
  if (clean.startsWith('```')) {
    const firstNewline = clean.indexOf('\n')
    if (firstNewline !== -1) {
      clean = clean.slice(firstNewline + 1)
    }
    if (clean.endsWith('```')) {
      clean = clean.slice(0, -3)
    }
  }
  return clean.trim()
}

function clampScore(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(100, Math.round(n)))
}

function clampConfidence(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(1, n))
}

function parseDimension(raw: unknown): RpEvalDimension | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const item = raw as Record<string, unknown>
  const id = String(item.id ?? '').trim()
  if (!id) return null
  const issuesRaw = item.issues
  const issues = Array.isArray(issuesRaw)
    ? issuesRaw.map((x) => String(x)).filter(Boolean)
    : []
  return {
    id,
    name: String(item.name ?? id),
    score: clampScore(item.score),
    confidence: clampConfidence(item.confidence),
    evidence: String(item.evidence ?? ''),
    issues,
  }
}

function parseModule(raw: unknown): RpEvalModuleResult {
  const fallback: RpEvalModuleResult = {
    available: false,
    subscore: 0,
    confidence: 0,
    dimensions: [],
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return fallback
  const item = raw as Record<string, unknown>
  const available = Boolean(item.available)
  const dimsRaw = item.dimensions
  const dimensions = Array.isArray(dimsRaw)
    ? dimsRaw.map(parseDimension).filter((d): d is RpEvalDimension => d !== null)
    : []
  return {
    available,
    subscore: clampScore(item.subscore),
    confidence: clampConfidence(item.confidence),
    dimensions,
  }
}

function parseCross(raw: unknown): RpEvalCrossConsistency {
  const fallback: RpEvalCrossConsistency = {
    available: false,
    score: 0,
    confidence: 0,
    notes: '',
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return fallback
  const item = raw as Record<string, unknown>
  return {
    available: Boolean(item.available),
    score: clampScore(item.score),
    confidence: clampConfidence(item.confidence),
    notes: String(item.notes ?? ''),
  }
}

export function parseRpEvalJson(text: string): ParseRpEvalResult {
  if (!text.trim()) {
    return { ok: false, error: '测评输出为空' }
  }
  try {
    const parsed = JSON.parse(stripMarkdownFence(text)) as Record<string, unknown>
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ok: false, error: '测评输出须为 JSON 对象' }
    }
    const recs = parsed.recommendations
    const recommendations = Array.isArray(recs)
      ? recs.map((x) => String(x)).filter(Boolean)
      : []

    const data: RpEvalParsed = {
      overall_score: clampScore(parsed.overall_score),
      overall_confidence: clampConfidence(parsed.overall_confidence),
      summary: String(parsed.summary ?? ''),
      segment_compress: parseModule(parsed.segment_compress),
      history_merge: parseModule(parsed.history_merge),
      cross_consistency: parseCross(parsed.cross_consistency),
      recommendations,
    }
    return { ok: true, data }
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'JSON 解析失败',
    }
  }
}
