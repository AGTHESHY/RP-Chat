export type JailbreakVariableGroup = 'nsfw' | 'general' | 'custom'

import { randomUUID } from './randomId'

export interface JailbreakVariableModule {
  id: string
  key: string
  label: string
  body: string
  enabled: boolean
  group: JailbreakVariableGroup
  order: number
}

export interface JailbreakBaseSection {
  id: string
  name: string
  content: string
  alwaysOn: boolean
  order: number
}

export interface JailbreakModulesDoc {
  baseSections: JailbreakBaseSection[]
  variables: JailbreakVariableModule[]
}

export type JailbreakContentMode = 'plain' | 'variable'

const NSFW_KEY_RE =
  /nsfw|NSFW|色情|瑟瑟|H特|H小说|エロ|H-Guide|sex_guide|nsfw必开/i

const SETVAR_CLEAR_RE = /\{\{setvar::([^:]+)::\s*\}\}/g
const SETVAR_BODY_RE = /\{\{setvar::([^:]+)::\s*([\s\S]*?)\}\}/g
const GETVAR_RE = /\{\{getvar::([^}]+)\}\}/g
const ST_TAG_RE = /\{\{[^}]+\}\}/g

const TAG_REF_BODY_RE = /^<([^>]+)>$/

function newId(): string {
  return randomUUID()
}

export function isNsfwKey(key: string, label = ''): boolean {
  return NSFW_KEY_RE.test(key) || NSFW_KEY_RE.test(label)
}

export function stripStSyntax(text: string): string {
  let out = text
  out = out.replace(/\{\{\/\/[\s\S]*?\}\}/g, '')
  out = out.replace(ST_TAG_RE, '')
  out = out.replace(/<!--[\s\S]*?-->/g, '')
  return out.replace(/\n{3,}/g, '\n\n').trim()
}

export function parseSetvarFromText(text: string): {
  clears: string[]
  bodies: Record<string, string>
} {
  const clears: string[] = []
  const bodies: Record<string, string> = {}
  let m: RegExpExecArray | null
  const clearRe = new RegExp(SETVAR_CLEAR_RE.source, 'g')
  while ((m = clearRe.exec(text)) !== null) {
    const key = m[1].trim()
    if (key && !bodies[key]) clears.push(key)
  }
  const bodyRe = new RegExp(SETVAR_BODY_RE.source, 'g')
  while ((m = bodyRe.exec(text)) !== null) {
    const key = m[1].trim()
    const body = m[2].trim()
    if (!key) continue
    if (body) bodies[key] = body
    else if (!bodies[key]) clears.push(key)
  }
  return { clears, bodies }
}

/** 从 prompt 文本中提取 <tagName>...</tagName> 整块（大小写不敏感） */
export function extractXmlBlock(text: string, tagName: string): string | null {
  const trimmed = tagName.trim()
  if (!trimmed) return null
  const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`<${escaped}>([\\s\\S]*?)</${escaped}>`, 'i')
  const m = text.match(re)
  if (!m) return null
  return `<${trimmed}>${m[1]}</${trimmed}>`
}

/** setvar 正文为 <标签> 引用时，用同 prompt 内 XML 块替换 */
export function resolveSetvarBody(
  raw: string,
  key: string,
  bodyFromSetvar: string,
): string {
  const trimmed = bodyFromSetvar.trim()
  if (!trimmed) return ''

  const tagRef = trimmed.match(TAG_REF_BODY_RE)
  if (tagRef) {
    const tag = tagRef[1].trim()
    const block =
      extractXmlBlock(raw, tag) ||
      extractXmlBlock(raw, key) ||
      extractXmlBlock(raw, tag.replace(/^\/|\/$/g, ''))
    if (block && block.length > trimmed.length) return block
  }

  if (trimmed.length < 40) {
    const byKey = extractXmlBlock(raw, key)
    if (byKey && byKey.length > trimmed.length) return byKey
  }

  return bodyFromSetvar
}

function isOnlySetvarClears(content: string): boolean {
  const stripped = content.replace(SETVAR_CLEAR_RE, '').replace(/\s/g, '')
  return stripped.length === 0 && SETVAR_CLEAR_RE.test(content)
}

function resolveGetvars(text: string, doc: JailbreakModulesDoc): string {
  const varMap = new Map(doc.variables.map((v) => [v.key, v]))
  return text.replace(GETVAR_RE, (_, rawKey: string) => {
    const key = rawKey.trim()
    const mod = varMap.get(key)
    if (!mod || !mod.enabled) return ''
    return mod.body
  })
}

export function composeJailbreakSp(doc: JailbreakModulesDoc): string {
  const parts: string[] = []

  const bases = [...doc.baseSections].sort((a, b) => a.order - b.order)
  for (const base of bases) {
    if (!base.alwaysOn) continue
    const resolved = resolveGetvars(base.content, doc).trim()
    if (resolved) parts.push(resolved)
  }

  const vars = [...doc.variables]
    .filter((v) => v.enabled)
    .sort((a, b) => a.order - b.order)
  for (const v of vars) {
    const resolved = resolveGetvars(v.body, doc).trim()
    if (resolved) parts.push(resolved)
  }

  for (const base of bases) {
    if (base.alwaysOn) continue
    const resolved = resolveGetvars(base.content, doc).trim()
    if (resolved) parts.push(resolved)
  }

  return parts.join('\n\n')
}

export function exportCleanJailbreakSp(doc: JailbreakModulesDoc): string {
  return stripStSyntax(composeJailbreakSp(doc))
}

export function createEmptyModulesDoc(): JailbreakModulesDoc {
  return { baseSections: [], variables: [] }
}

interface StPrompt {
  identifier?: string
  name?: string
  enabled?: boolean
  content?: string
}

export interface StPreset {
  prompts?: StPrompt[]
  prompt_order?: { order?: { identifier?: string; enabled?: boolean }[] }[]
}

interface CollectedVar {
  key: string
  body: string
  label: string
  order: number
}

function getOrderedIds(data: StPreset, byId: Map<string, StPrompt>): string[] {
  const orderedIds: string[] = []
  const seen = new Set<string>()
  for (const block of data.prompt_order ?? []) {
    for (const entry of block.order ?? []) {
      const id = entry.identifier
      if (!id || seen.has(id) || !byId.has(id)) continue
      seen.add(id)
      orderedIds.push(id)
    }
  }
  if (!orderedIds.length) {
    for (const p of data.prompts ?? []) {
      if (p.identifier && p.enabled !== false) orderedIds.push(p.identifier)
    }
  }
  return orderedIds
}

function getEnabledOrderedIds(data: StPreset, byId: Map<string, StPrompt>): string[] {
  const orderedIds: string[] = []
  const seen = new Set<string>()
  for (const block of data.prompt_order ?? []) {
    for (const entry of block.order ?? []) {
      if (!entry.enabled) continue
      const id = entry.identifier
      if (!id || seen.has(id) || !byId.has(id)) continue
      seen.add(id)
      orderedIds.push(id)
    }
  }
  return orderedIds
}

/** 按 prompt_order 全局顺序记录 key 首次出现位置 */
function buildKeyOrderMap(data: StPreset, byId: Map<string, StPrompt>): Map<string, number> {
  const keyOrder = new Map<string, number>()
  let idx = 0
  const registerKeys = (raw: string) => {
    const { clears, bodies } = parseSetvarFromText(raw)
    for (const k of clears) {
      if (!keyOrder.has(k)) keyOrder.set(k, idx++)
    }
    for (const k of Object.keys(bodies)) {
      if (!keyOrder.has(k)) keyOrder.set(k, idx++)
    }
  }

  for (const id of getOrderedIds(data, byId)) {
    const raw = (byId.get(id)?.content || '').trim()
    if (raw) registerKeys(raw)
  }

  for (const p of data.prompts ?? []) {
    const raw = (p.content || '').trim()
    if (raw) registerKeys(raw)
  }

  return keyOrder
}

/** ST 中 enabled 条目里对该 key 有非空 setvar 赋值 */
function collectStEnabledAssignKeys(
  data: StPreset,
  byId: Map<string, StPrompt>,
): Set<string> {
  const keys = new Set<string>()
  for (const id of getEnabledOrderedIds(data, byId)) {
    const raw = (byId.get(id)?.content || '').trim()
    if (!raw) continue
    const { bodies } = parseSetvarFromText(raw)
    for (const [k, b] of Object.entries(bodies)) {
      const resolved = resolveSetvarBody(raw, k, b)
      if (resolved.trim()) keys.add(k)
    }
  }
  return keys
}

export function buildDefaultEnabled(
  key: string,
  label: string,
  stEnabledAssignKeys: Set<string>,
): boolean {
  if (isNsfwKey(key, label)) return true
  return stEnabledAssignKeys.has(key)
}

/** 扫描全部 prompts，合并每个 setvar key 的最长正文 */
export function collectAllSetvarKeys(data: StPreset): CollectedVar[] {
  const byId = new Map<string, StPrompt>()
  for (const p of data.prompts ?? []) {
    if (p.identifier) byId.set(p.identifier, p)
  }
  const keyOrder = buildKeyOrderMap(data, byId)
  const merged = new Map<string, CollectedVar>()

  const upsert = (key: string, body: string, promptName: string) => {
    const resolved = body
    const existing = merged.get(key)
    if (!existing) {
      merged.set(key, {
        key,
        body: resolved,
        label: promptName,
        order: keyOrder.get(key) ?? merged.size,
      })
      return
    }
    if (resolved.length > existing.body.length) {
      existing.body = resolved
      existing.label = promptName
    }
  }

  for (const p of data.prompts ?? []) {
    const raw = (p.content || '').trim()
    if (!raw) continue
    const name = (p.name || p.identifier || '').trim()
    const { clears, bodies } = parseSetvarFromText(raw)

    for (const key of clears) {
      if (!merged.has(key)) {
        upsert(key, '', name || key)
      }
    }

    for (const [key, bodyRaw] of Object.entries(bodies)) {
      const resolved = stripStSyntax(resolveSetvarBody(raw, key, bodyRaw))
      upsert(key, resolved, name !== key ? `${name} · ${key}` : key)
    }
  }

  return [...merged.values()].sort((a, b) => a.order - b.order)
}

export function parseShuangrenPreset(data: StPreset): JailbreakModulesDoc {
  const promptsList = data.prompts ?? []
  const byId = new Map<string, StPrompt>()
  for (const p of promptsList) {
    if (p.identifier) byId.set(p.identifier, p)
  }

  const enabledOrderedIds = getEnabledOrderedIds(data, byId)
  const stEnabledAssignKeys = collectStEnabledAssignKeys(data, byId)

  const collected = collectAllSetvarKeys(data)
  const variables: JailbreakVariableModule[] = collected.map((item, index) => {
    const nsfw = isNsfwKey(item.key, item.label)
    return {
      id: newId(),
      key: item.key,
      label: item.label || item.key,
      body: item.body,
      enabled: buildDefaultEnabled(item.key, item.label, stEnabledAssignKeys),
      group: nsfw ? 'nsfw' : 'general',
      order: item.order ?? index,
    }
  })

  const baseSections: JailbreakBaseSection[] = []
  let baseOrder = 0

  for (const id of enabledOrderedIds) {
    const pr = byId.get(id)!
    const name = (pr.name || id).trim()
    const raw = (pr.content || '').trim()
    if (!raw) continue

    if (id === 'main' && !isOnlySetvarClears(raw)) {
      baseSections.push({
        id: newId(),
        name,
        content: stripStSyntax(raw),
        alwaysOn: true,
        order: baseOrder++,
      })
      continue
    }

    if (isOnlySetvarClears(raw)) continue

    const { bodies } = parseSetvarFromText(raw)
    const bodyKeys = Object.keys(bodies)
    if (bodyKeys.length > 0) continue

    const withoutSetvar = raw.replace(SETVAR_BODY_RE, '').replace(SETVAR_CLEAR_RE, '').trim()
    const hasGetvar = GETVAR_RE.test(raw)
    if (hasGetvar || withoutSetvar.length > 20) {
      baseSections.push({
        id: newId(),
        name,
        content: raw,
        alwaysOn: false,
        order: baseOrder++,
      })
    }
  }

  return { baseSections, variables }
}

export function addCustomVariable(
  doc: JailbreakModulesDoc,
  partial?: Partial<Pick<JailbreakVariableModule, 'key' | 'label' | 'body' | 'enabled'>>,
): JailbreakVariableModule {
  const maxOrder = doc.variables.reduce((m, v) => Math.max(m, v.order), -1)
  const mod: JailbreakVariableModule = {
    id: newId(),
    key: partial?.key?.trim() || `custom_${Date.now()}`,
    label: partial?.label?.trim() || '自定义开关',
    body: partial?.body ?? '',
    enabled: partial?.enabled ?? true,
    group: 'custom',
    order: maxOrder + 1,
  }
  doc.variables.push(mod)
  return mod
}

export function reorderVariable(doc: JailbreakModulesDoc, id: string, delta: number): void {
  const sorted = [...doc.variables].sort((a, b) => a.order - b.order)
  const idx = sorted.findIndex((v) => v.id === id)
  if (idx < 0) return
  const swap = idx + delta
  if (swap < 0 || swap >= sorted.length) return
  const a = sorted[idx]
  const b = sorted[swap]
  const tmp = a.order
  a.order = b.order
  b.order = tmp
}
