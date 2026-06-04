import { stripMarkdownFence } from './parseRpEvalJson'

export type BrainRecommendation = 'minor' | 'major' | 'hold'

export interface BrainModuleAdvice {
  prompt_type: 'segment_compress' | 'history_merge'
  evaluated_version: string
  base_version: string
  recommendation: BrainRecommendation
  suggested_version_name?: string
  target_base_version?: string
  rationale: string
  focus_areas: string[]
}

export interface BrainParsed {
  overall: BrainRecommendation
  overall_rationale: string
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

function parseRecommendation(raw: unknown): BrainRecommendation {
  const v = String(raw ?? '').trim() as BrainRecommendation
  return VALID_OVERALL.has(v) ? v : 'hold'
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
    const data: BrainParsed = {
      overall: parseRecommendation(parsed.overall),
      overall_rationale: String(parsed.overall_rationale ?? ''),
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

export function isValidSuggestedVersionName(name: string): boolean {
  const n = name.trim()
  if (!n || n === 'v1' || n === 'v2') return false
  return /^[a-zA-Z][a-zA-Z0-9_]*$/.test(n)
}
