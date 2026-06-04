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

export interface RpEvalModelScore {
  model: string
  overall_score: number
  overall_confidence: number
  summary: string
  segment_compress: RpEvalModuleResult
  history_merge: RpEvalModuleResult
  cross_consistency: RpEvalCrossConsistency
}

export interface RpEvalCrossModelComparison {
  available: boolean
  score: number
  confidence: number
  notes: string
  ranking: string[]
  dimension_highlights: { dimension: string; best_model: string; notes: string }[]
}

export type RpEvalMode = 'single' | 'multi_compare'

export interface RpEvalParsed {
  eval_mode: RpEvalMode
  overall_score: number
  overall_confidence: number
  summary: string
  segment_compress: RpEvalModuleResult
  history_merge: RpEvalModuleResult
  cross_consistency: RpEvalCrossConsistency
  model_scores: RpEvalModelScore[]
  cross_model_comparison: RpEvalCrossModelComparison | null
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

function parseModelScore(raw: unknown): RpEvalModelScore | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const item = raw as Record<string, unknown>
  const model = String(item.model ?? '').trim()
  if (!model) return null
  return {
    model,
    overall_score: clampScore(item.overall_score),
    overall_confidence: clampConfidence(item.overall_confidence),
    summary: String(item.summary ?? ''),
    segment_compress: parseModule(item.segment_compress),
    history_merge: parseModule(item.history_merge),
    cross_consistency: parseCross(item.cross_consistency),
  }
}

function parseCrossModelComparison(raw: unknown): RpEvalCrossModelComparison | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const item = raw as Record<string, unknown>
  const rankingRaw = item.ranking
  const ranking = Array.isArray(rankingRaw)
    ? rankingRaw.map((x) => String(x)).filter(Boolean)
    : []
  const highlightsRaw = item.dimension_highlights
  const dimension_highlights = Array.isArray(highlightsRaw)
    ? highlightsRaw
        .map((h) => {
          if (!h || typeof h !== 'object' || Array.isArray(h)) return null
          const row = h as Record<string, unknown>
          return {
            dimension: String(row.dimension ?? ''),
            best_model: String(row.best_model ?? ''),
            notes: String(row.notes ?? ''),
          }
        })
        .filter((x): x is { dimension: string; best_model: string; notes: string } => x !== null)
    : []
  return {
    available: Boolean(item.available),
    score: clampScore(item.score),
    confidence: clampConfidence(item.confidence),
    notes: String(item.notes ?? ''),
    ranking,
    dimension_highlights,
  }
}

export function isMultiCompareEval(data: RpEvalParsed): boolean {
  return data.eval_mode === 'multi_compare' && data.model_scores.length > 1
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

    const modelScoresRaw = parsed.model_scores
    const model_scores = Array.isArray(modelScoresRaw)
      ? modelScoresRaw.map(parseModelScore).filter((m): m is RpEvalModelScore => m !== null)
      : []

    const evalModeRaw = String(parsed.eval_mode ?? '')
    const eval_mode: RpEvalMode =
      evalModeRaw === 'multi_compare' || model_scores.length > 1
        ? 'multi_compare'
        : 'single'

    const cross_model_comparison = parseCrossModelComparison(parsed.cross_model_comparison)

    let segment_compress = parseModule(parsed.segment_compress)
    let history_merge = parseModule(parsed.history_merge)
    let cross_consistency = parseCross(parsed.cross_consistency)

    if (eval_mode === 'multi_compare' && model_scores.length > 0) {
      const first = model_scores[0]
      if (!segment_compress.available && first) {
        segment_compress = first.segment_compress
        history_merge = first.history_merge
        cross_consistency = first.cross_consistency
      }
    }

    const data: RpEvalParsed = {
      eval_mode,
      overall_score: clampScore(parsed.overall_score),
      overall_confidence: clampConfidence(parsed.overall_confidence),
      summary: String(parsed.summary ?? ''),
      segment_compress,
      history_merge,
      cross_consistency,
      model_scores,
      cross_model_comparison,
      recommendations,
    }

    if (eval_mode === 'single' && model_scores.length === 0) {
      data.model_scores = []
    }

    return { ok: true, data }
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'JSON 解析失败',
    }
  }
}

export function formatEvaluatedModelsLabel(models: string[]): string {
  if (models.length === 0) return '—'
  if (models.length <= 2) return models.join('、')
  return `${models.length} 个模型`
}
