import type { BrainModuleAdvice, BrainRevisionPlan, BrainRevisionPlanItem } from './parseBrainJson'

function toPlanItems(lines: string[], sectionPrefix: string): BrainRevisionPlanItem[] {
  return lines
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => ({
      section: sectionPrefix,
      action: 'modify',
      summary: line,
      detail: line,
    }))
}

/** 智脑未输出 revision_plan 时，用 focus_areas / linked_issues 生成展示与修订依据 */
export function resolveRevisionPlan(
  mod: BrainModuleAdvice,
  linkedIssues: string[] = [],
): BrainRevisionPlan {
  if (mod.revision_plan && (mod.revision_plan.sfw.length > 0 || mod.revision_plan.nsfw.length > 0)) {
    return mod.revision_plan
  }

  const typeLabel =
    mod.prompt_type === 'segment_compress' ? 'Segment 压缩' : 'History 合并'

  const sfwFromFocus = toPlanItems(mod.focus_areas, `${typeLabel} · SFW 规则`)
  const nsfwFromFocus = toPlanItems(mod.focus_areas, `${typeLabel} · NSFW 规则`)
  const sfwFromIssues = toPlanItems(linkedIssues, `${typeLabel} · 关联问题（SFW）`)
  const nsfwFromIssues = toPlanItems(linkedIssues, `${typeLabel} · 关联问题（NSFW）`)

  return {
    sfw: sfwFromFocus.length > 0 ? sfwFromFocus : sfwFromIssues,
    nsfw: nsfwFromFocus.length > 0 ? nsfwFromFocus : nsfwFromIssues,
  }
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
