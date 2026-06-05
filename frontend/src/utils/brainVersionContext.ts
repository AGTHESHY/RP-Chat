import { getVersionMeta, type VersionsListResponse } from '../api'
import {
  rootBaselineForVersion,
  type BaselineVersion,
  type VersionNode,
} from './versionTree'

export type VersionKind = 'baseline' | 'custom_fork'

export interface BrainVersionContext {
  evaluated_version: string
  is_baseline: boolean
  base_version: string
  root_baseline: BaselineVersion
  parent_chain: string[]
  version_kind: VersionKind
  status: string
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

async function walkParentChain(startVersion: string): Promise<string[]> {
  const chain: string[] = [startVersion]
  let current: string | undefined = startVersion
  const visited = new Set<string>([startVersion])

  while (current && current !== 'v1' && current !== 'v2') {
    try {
      const meta = await getVersionMeta(current)
      const parent = meta.base_version?.trim()
      if (!parent || visited.has(parent)) break
      chain.push(parent)
      visited.add(parent)
      current = parent
    } catch {
      break
    }
  }
  return chain
}

export async function buildVersionContext(
  version: string,
  catalog: VersionsListResponse,
): Promise<BrainVersionContext> {
  const meta = await getVersionMeta(version)
  const nodes = buildVersionNodes(catalog)
  const root = rootBaselineForVersion(nodes, version)
  const isBaseline = Boolean(meta.is_baseline) || version === 'v1' || version === 'v2'
  const parent_chain = await walkParentChain(version)

  return {
    evaluated_version: version,
    is_baseline: isBaseline,
    base_version: meta.base_version || (isBaseline ? version : ''),
    root_baseline: root,
    parent_chain,
    version_kind: isBaseline ? 'baseline' : 'custom_fork',
    status: meta.status || '',
  }
}

export function formatVersionKindLabel(ctx: BrainVersionContext): string {
  if (ctx.is_baseline) return `基线 ${ctx.evaluated_version}`
  const parent = ctx.base_version || ctx.root_baseline
  return `基于 ${parent} 迭代 · ${ctx.evaluated_version}`
}
