import type { BrainRevisionBatchModulePayload } from '../api'
import { resolveRevisionPlan } from './brainRevisionDisplay'
import {
  isValidSuggestedVersionName,
  type BrainModuleAdvice,
  type BrainParsed,
} from './parseBrainJson'

export function getMinorRevisionModules(parsed: BrainParsed): BrainModuleAdvice[] {
  return parsed.modules.filter((mod) => mod.recommendation === 'minor')
}

export function linkedIssuesForModule(
  parsed: BrainParsed,
  mod: BrainModuleAdvice,
): string[] {
  return (
    parsed.sp_improvements.find((item) => item.prompt_type === mod.prompt_type)
      ?.linked_issues ?? []
  )
}

export function pickIterationVersionName(parsed: BrainParsed): string | null {
  const names = getMinorRevisionModules(parsed)
    .map((mod) => mod.suggested_version_name?.trim())
    .filter((name): name is string => Boolean(name && isValidSuggestedVersionName(name)))
  return names[0] ?? null
}

export function pickForkBaseVersion(parsed: BrainParsed): string | null {
  const minor = getMinorRevisionModules(parsed)
  const mod = minor[0]
  if (!mod) return null
  return mod.evaluated_version || mod.base_version || null
}

export function canCreateBrainIteration(parsed: BrainParsed): boolean {
  const minor = getMinorRevisionModules(parsed)
  if (minor.length === 0) return false
  return Boolean(pickIterationVersionName(parsed))
}

export function buildBrainRevisionBatchModules(
  parsed: BrainParsed,
): BrainRevisionBatchModulePayload[] {
  return getMinorRevisionModules(parsed).map((mod) => {
    const linked = linkedIssuesForModule(parsed, mod)
    return {
      prompt_type: mod.prompt_type,
      focus_areas: mod.focus_areas,
      linked_issues: linked,
      rationale: mod.rationale,
      revision_plan: resolveRevisionPlan(mod, linked),
    }
  })
}

export function moduleLabel(promptType: string): string {
  return promptType === 'segment_compress' ? 'Segment 压缩' : 'History 合并'
}
