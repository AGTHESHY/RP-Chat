import { stripMarkdownFence } from './parseRpEvalJson'

export type BrainRecommendation = 'minor' | 'major' | 'hold'
export type BrainDevPotential = 'high' | 'medium' | 'low'

export interface BrainSpImprovement {
  prompt_type: 'segment_compress' | 'history_merge'
  focus_areas: string[]
  linked_issues: string[]
}

export interface BrainRpModelInsightItem {
  model: string
  overall_score: number
  dev_potential: BrainDevPotential
  sp_actionable_issues: string[]
  summary: string
}

export interface BrainRpModelInsights {
  available: boolean
  highest_dev_potential: string
  ranking: string[]
  notes: string
  per_model: BrainRpModelInsightItem[]
}

export interface BrainRevisionPlanItem {
  section: string
  action: 'add' | 'modify' | 'remove' | 'clarify' | string
  summary: string
  detail: string
}

export interface BrainRevisionPlan {
  sfw: BrainRevisionPlanItem[]
  nsfw: BrainRevisionPlanItem[]
}

export interface BrainModuleAdvice {
  prompt_type: 'segment_compress' | 'history_merge'
  evaluated_version: string
  base_version: string
  recommendation: BrainRecommendation
  suggested_version_name?: string
  target_base_version?: string
  rationale: string
  focus_areas: string[]
  revision_plan?: BrainRevisionPlan
}

export interface BrainParsed {
  overall: BrainRecommendation
  overall_rationale: string
  sp_improvements: BrainSpImprovement[]
  rp_model_insights: BrainRpModelInsights
  modules: BrainModuleAdvice[]
  next_steps: string[]
}

export interface ParseBrainResult {
  ok: boolean
  error?: string
  data?: BrainParsed
}

const VALID_OVERALL = new Set<BrainRecommendation>(['minor', 'major', 'hold'])
const VALID_TYPES = new Set(['segment_compress', 'history_merge'])
const VALID_DEV_POTENTIAL = new Set<BrainDevPotential>(['high', 'medium', 'low'])

function parseRecommendation(raw: unknown): BrainRecommendation {
  const v = String(raw ?? '').trim() as BrainRecommendation
  return VALID_OVERALL.has(v) ? v : 'hold'
}

function parseDevPotential(raw: unknown): BrainDevPotential {
  const v = String(raw ?? '').trim() as BrainDevPotential
  return VALID_DEV_POTENTIAL.has(v) ? v : 'medium'
}

function parseSpImprovement(raw: unknown): BrainSpImprovement | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const item = raw as Record<string, unknown>
  const promptType = String(item.prompt_type ?? '').trim()
  if (!VALID_TYPES.has(promptType)) return null
  const focusRaw = item.focus_areas
  const linkedRaw = item.linked_issues
  return {
    prompt_type: promptType as BrainSpImprovement['prompt_type'],
    focus_areas: Array.isArray(focusRaw)
      ? focusRaw.map((x) => String(x)).filter(Boolean)
      : [],
    linked_issues: Array.isArray(linkedRaw)
      ? linkedRaw.map((x) => String(x)).filter(Boolean)
      : [],
  }
}

function parseRpModelInsightItem(raw: unknown): BrainRpModelInsightItem | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const item = raw as Record<string, unknown>
  const model = String(item.model ?? '').trim()
  if (!model) return null
  const issuesRaw = item.sp_actionable_issues
  return {
    model,
    overall_score: Math.max(0, Math.min(100, Math.round(Number(item.overall_score) || 0))),
    dev_potential: parseDevPotential(item.dev_potential),
    sp_actionable_issues: Array.isArray(issuesRaw)
      ? issuesRaw.map((x) => String(x)).filter(Boolean)
      : [],
    summary: String(item.summary ?? ''),
  }
}

function parseRpModelInsights(raw: unknown): BrainRpModelInsights {
  const fallback: BrainRpModelInsights = {
    available: false,
    highest_dev_potential: '',
    ranking: [],
    notes: '',
    per_model: [],
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return fallback
  const item = raw as Record<string, unknown>
  const rankingRaw = item.ranking
  const perModelRaw = item.per_model
  return {
    available: Boolean(item.available),
    highest_dev_potential: String(item.highest_dev_potential ?? ''),
    ranking: Array.isArray(rankingRaw)
      ? rankingRaw.map((x) => String(x)).filter(Boolean)
      : [],
    notes: String(item.notes ?? ''),
    per_model: Array.isArray(perModelRaw)
      ? perModelRaw.map(parseRpModelInsightItem).filter((m): m is BrainRpModelInsightItem => m !== null)
      : [],
  }
}

function parseRevisionPlanItem(raw: unknown): BrainRevisionPlanItem | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const item = raw as Record<string, unknown>
  const summary = String(item.summary ?? item.title ?? '').trim()
  const detail = String(item.detail ?? item.description ?? summary).trim()
  if (!summary && !detail) return null
  return {
    section: String(item.section ?? item.target ?? '未命名区块').trim() || '未命名区块',
    action: String(item.action ?? 'modify').trim() || 'modify',
    summary: summary || detail,
    detail: detail || summary,
  }
}

function parseRevisionPlan(raw: unknown): BrainRevisionPlan | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const item = raw as Record<string, unknown>
  const sfwRaw = item.sfw
  const nsfwRaw = item.nsfw
  const sfw = Array.isArray(sfwRaw)
    ? sfwRaw.map(parseRevisionPlanItem).filter((x): x is BrainRevisionPlanItem => x !== null)
    : []
  const nsfw = Array.isArray(nsfwRaw)
    ? nsfwRaw.map(parseRevisionPlanItem).filter((x): x is BrainRevisionPlanItem => x !== null)
    : []
  if (sfw.length === 0 && nsfw.length === 0) return undefined
  return { sfw, nsfw }
}

function parseModuleAdvice(raw: unknown): BrainModuleAdvice | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const item = raw as Record<string, unknown>
  const promptType = String(item.prompt_type ?? '').trim()
  if (!VALID_TYPES.has(promptType)) return null
  const evaluated = String(item.evaluated_version ?? '').trim()
  if (!evaluated) return null
  const focusRaw = item.focus_areas
  const focus_areas = Array.isArray(focusRaw)
    ? focusRaw.map((x) => String(x)).filter(Boolean)
    : []
  const rec = parseRecommendation(item.recommendation)
  const suggested = String(item.suggested_version_name ?? '').trim() || undefined
  const targetBase = String(item.target_base_version ?? '').trim() || undefined
  return {
    prompt_type: promptType as BrainModuleAdvice['prompt_type'],
    evaluated_version: evaluated,
    base_version: String(item.base_version ?? '').trim(),
    recommendation: rec,
    suggested_version_name: suggested,
    target_base_version: targetBase,
    rationale: String(item.rationale ?? ''),
    focus_areas,
    revision_plan: parseRevisionPlan(item.revision_plan),
  }
}

export function parseBrainJson(text: string): ParseBrainResult {
  if (!text.trim()) {
    return { ok: false, error: '智脑输出为空' }
  }
  try {
    const parsed = JSON.parse(stripMarkdownFence(text)) as Record<string, unknown>
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ok: false, error: '智脑输出须为 JSON 对象' }
    }
    const modulesRaw = parsed.modules
    const modules = Array.isArray(modulesRaw)
      ? modulesRaw.map(parseModuleAdvice).filter((m): m is BrainModuleAdvice => m !== null)
      : []
    const stepsRaw = parsed.next_steps
    const next_steps = Array.isArray(stepsRaw)
      ? stepsRaw.map((x) => String(x)).filter(Boolean)
      : []
    const spRaw = parsed.sp_improvements
    const sp_improvements = Array.isArray(spRaw)
      ? spRaw.map(parseSpImprovement).filter((s): s is BrainSpImprovement => s !== null)
      : []

    const data: BrainParsed = {
      overall: parseRecommendation(parsed.overall),
      overall_rationale: String(parsed.overall_rationale ?? ''),
      sp_improvements,
      rp_model_insights: parseRpModelInsights(parsed.rp_model_insights),
      modules,
      next_steps,
    }
    return { ok: true, data }
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'JSON 解析失败',
    }
  }
}

export function brainRecommendationLabel(rec: BrainRecommendation): string {
  if (rec === 'minor') return '小版本更迭'
  if (rec === 'major') return '大版本换代'
  return '维持现状'
}

export function devPotentialLabel(p: BrainDevPotential): string {
  if (p === 'high') return '高'
  if (p === 'low') return '低'
  return '中'
}

export function isValidSuggestedVersionName(name: string): boolean {
  const n = name.trim()
  if (!n || n === 'v1' || n === 'v2') return false
  return /^[a-zA-Z][a-zA-Z0-9_]*$/.test(n)
}

/** @deprecated 使用 canCreateBrainIteration(parsed) */
export function needsAiAutoRevision(mod: BrainModuleAdvice): boolean {
  return mod.recommendation === 'minor' && Boolean(mod.suggested_version_name)
}
