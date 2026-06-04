import {
  getVersionMeta,
  getVersionPrompt,
  type PromptType,
  type RpEvalDetail,
  type VersionsListResponse,
} from '../api'
import {
  rootBaselineForVersion,
  type BaselineVersion,
  type VersionNode,
} from './versionTree'

export interface BrainVersionGuardResult {
  ok: boolean
  message?: string
}

function normalizePromptContent(text: string): string {
  return text.replace(/\r\n/g, '\n').trim().replace(/\n{3,}/g, '\n\n')
}

async function fetchPromptContent(version: string, promptType: PromptType): Promise<string> {
  const prompt = await getVersionPrompt(version, promptType, 'zh', true)
  return normalizePromptContent(prompt.content || '')
}

function buildVersionNodes(catalog: VersionsListResponse): VersionNode[] {
  return [
    ...catalog.custom.map((item) => ({
      version: item.version,
      base_version: item.base_version,
      status: item.status,
    })),
    ...catalog.drafts.map((item) => ({
      version: item.version,
      base_version: item.base_version,
      status: 'draft',
    })),
  ]
}

/** 同一基线（v1/v2）下的基线名 + 所有自定义/草稿版本 */
function versionsUnderSameRoot(nodes: VersionNode[], root: BaselineVersion): string[] {
  const seen = new Set<string>([root])
  for (const node of nodes) {
    if (rootBaselineForVersion(nodes, node.version) === root) {
      seen.add(node.version)
    }
  }
  return [...seen]
}

async function walkParentVersions(startVersion: string): Promise<string[]> {
  const chain: string[] = []
  let current: string | undefined = startVersion
  const visited = new Set<string>()
  while (current && !visited.has(current)) {
    visited.add(current)
    if (current === 'v1' || current === 'v2') {
      chain.push(current)
      break
    }
    try {
      const meta = await getVersionMeta(current)
      const parent = meta.base_version?.trim()
      if (!parent) break
      chain.push(parent)
      current = parent
    } catch {
      break
    }
  }
  return chain
}

interface ModuleCheck {
  version: string
  promptType: PromptType
  label: string
}

async function validateOneModule(
  check: ModuleCheck,
  nodes: VersionNode[],
): Promise<BrainVersionGuardResult> {
  const meta = await getVersionMeta(check.version)
  const root = rootBaselineForVersion(nodes, check.version)
  const evaluatedContent = await fetchPromptContent(check.version, check.promptType)

  if (meta.is_baseline || check.version === root) {
    return {
      ok: false,
      message: `${check.label}：被测版本「${check.version}」为只读基线，请先 fork 出有差异的自定义版本并完成 RP 测评后再分析`,
    }
  }

  const baselineContent = await fetchPromptContent(root, check.promptType)
  if (evaluatedContent === baselineContent) {
    return {
      ok: false,
      message: `${check.label}：版本「${check.version}」与基线「${root}」正文相同，请换用有改动的版本后再分析`,
    }
  }

  const compareVersions = new Set<string>()
  for (const v of versionsUnderSameRoot(nodes, root)) {
    if (v !== check.version) compareVersions.add(v)
  }
  for (const v of await walkParentVersions(check.version)) {
    if (v !== check.version) compareVersions.add(v)
  }

  for (const other of compareVersions) {
    try {
      const otherContent = await fetchPromptContent(other, check.promptType)
      if (evaluatedContent === otherContent) {
        const relation =
          other === root
            ? `基线「${other}」`
            : other === meta.base_version
              ? `上游版本「${other}」`
              : `版本「${other}」`
        return {
          ok: false,
          message: `${check.label}：「${check.version}」与${relation}正文相同，请换用不同版本后再分析`,
        }
      }
    } catch {
      /* 忽略无法加载的对比版本 */
    }
  }

  return { ok: true }
}

/**
 * 被测 SP 若与基线或同基线/上游链上任意版本正文一致，则无需智脑分析。
 */
export async function validateBrainEvalVersions(
  evalDetail: RpEvalDetail,
  catalog: VersionsListResponse,
): Promise<BrainVersionGuardResult> {
  const nodes = buildVersionNodes(catalog)
  const checks: ModuleCheck[] = []

  if (evalDetail.has_compress && evalDetail.compress_prompt_version) {
    checks.push({
      version: evalDetail.compress_prompt_version,
      promptType: 'segment_compress',
      label: 'Segment 压缩',
    })
  }
  if (evalDetail.has_merge && evalDetail.merge_prompt_version) {
    checks.push({
      version: evalDetail.merge_prompt_version,
      promptType: 'history_merge',
      label: 'History 合并',
    })
  }

  if (checks.length === 0) {
    return { ok: false, message: '测评记录缺少可分析的 SP 版本信息' }
  }

  for (const check of checks) {
    const result = await validateOneModule(check, nodes)
    if (!result.ok) return result
  }

  return { ok: true }
}
