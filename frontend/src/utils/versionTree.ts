export interface VersionNode {
  version: string
  base_version: string
  status?: string
}

export interface VersionTreeNode {
  version: string
  status?: string
  children: VersionTreeNode[]
}

export type BaselineVersion = 'v1' | 'v2'

export function rootBaselineForVersion(
  nodes: VersionNode[],
  version: string,
  fallback: BaselineVersion = 'v2',
): BaselineVersion {
  if (version === 'v1' || version === 'v2') return version
  const parentMap = new Map(nodes.map((node) => [node.version, node.base_version]))
  let current: string | undefined = version
  while (current) {
    const parent = parentMap.get(current)
    if (parent === 'v1' || parent === 'v2') return parent
    if (!parent) break
    current = parent
  }
  return fallback
}

export function buildVersionTree(nodes: VersionNode[], baseline: BaselineVersion): VersionTreeNode[] {
  function belongsToBaseline(version: string): boolean {
    return rootBaselineForVersion(nodes, version, baseline) === baseline
  }

  function childrenOf(parent: string): VersionTreeNode[] {
    return nodes
      .filter((node) => node.base_version === parent && belongsToBaseline(node.version))
      .sort((a, b) => a.version.localeCompare(b.version))
      .map((node) => ({
        version: node.version,
        status: node.status,
        children: childrenOf(node.version),
      }))
  }

  return childrenOf(baseline)
}

/** 收集待删除版本（含 root），子版本在前、根在后 */
export function collectVersionSubtree(nodes: VersionNode[], root: string): string[] {
  const childrenByParent = new Map<string, string[]>()
  for (const node of nodes) {
    if (!node.base_version) continue
    const list = childrenByParent.get(node.base_version) ?? []
    list.push(node.version)
    childrenByParent.set(node.base_version, list)
  }

  const ordered: string[] = []
  const seen = new Set<string>()

  function walk(version: string) {
    if (seen.has(version)) return
    seen.add(version)
    for (const child of childrenByParent.get(version) ?? []) {
      walk(child)
    }
    ordered.push(version)
  }

  walk(root)
  return ordered
}
