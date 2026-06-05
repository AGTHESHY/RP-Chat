import type { BrainModuleAdvice, BrainRevisionPlan } from './parseBrainJson'

/** 仅使用智脑输出的 revision_plan；修订依据由 focus_areas / linked_issues 在 API 层补充 */
export function resolveRevisionPlan(
  mod: BrainModuleAdvice,
  _linkedIssues: string[] = [],
): BrainRevisionPlan {
  if (mod.revision_plan && (mod.revision_plan.sfw.length > 0 || mod.revision_plan.nsfw.length > 0)) {
    return mod.revision_plan
  }
  return { sfw: [], nsfw: [] }
}

export function revisionActionLabel(action: string): string {
  switch (action) {
    case 'add':
      return '新增'
    case 'modify':
      return '修改'
    case 'remove':
      return '删除'
    case 'clarify':
      return '澄清'
    default:
      return action || '修改'
  }
}
