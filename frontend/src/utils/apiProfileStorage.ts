import { decryptSecret, encryptSecret, isEncryptedSecret } from './secretStorage'
import {
  API_CONFIG_STORAGE_KEY,
  defaultApiConfig,
  normalizeBaseUrl,
  type ApiConfig,
} from './apiConfigStorage'

export const API_PROFILES_STORAGE_KEY = 'rp-chat-api-profiles'
export const RUNTIME_STORAGE_KEYS = {
  test: 'rp-chat-runtime-test',
  eval: 'rp-chat-runtime-eval',
  jailbreak: 'rp-chat-runtime-jailbreak',
  brain: 'rp-chat-runtime-brain',
} as const

export type RuntimeScope = keyof typeof RUNTIME_STORAGE_KEYS

/** DeepSeek JSON Output：{@link https://api-docs.deepseek.com/zh-cn/guides/json_mode} */
export const DEEPSEEK_JSON_OUTPUT_EXTRA: Record<string, unknown> = {
  response_format: { type: 'json_object' },
}

export interface ApiProfile {
  id: string
  name: string
  base_url: string
  api_key: string
  models: string[]
  /** 合并进 Chat Completions 请求体的额外字段（如 response_format） */
  extra_body: Record<string, unknown>
}

export interface ApiProfileRegistry {
  profiles: ApiProfile[]
}

export interface PageRuntimeConfig {
  apiProfileId: string
  modelName: string
  /** 测试页多模型并行；为空时回退为 modelName */
  modelNames?: string[]
  temperature: number
  top_k: number | null
}

export interface ResolvedRuntimeRequest {
  base_url: string
  api_key: string
  model: string
  temperature: number
  top_k: number | null
  extra_body: Record<string, unknown>
}

interface StoredApiProfile {
  id: string
  name: string
  base_url: string
  api_key: string
  models: string[]
  extra_body?: Record<string, unknown>
}

export function normalizeExtraBody(raw: unknown): Record<string, unknown> {
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    return { ...(raw as Record<string, unknown>) }
  }
  return {}
}

export function formatExtraBodyJson(extra: Record<string, unknown>): string {
  if (Object.keys(extra).length === 0) return '{}'
  return JSON.stringify(extra, null, 2)
}

export function parseExtraBodyJson(text: string): Record<string, unknown> {
  const trimmed = text.trim() || '{}'
  const parsed = JSON.parse(trimmed) as unknown
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('额外请求体须为 JSON 对象')
  }
  return parsed as Record<string, unknown>
}

interface StoredApiProfileRegistry {
  profiles: StoredApiProfile[]
}

export const defaultRuntimeConfig: PageRuntimeConfig = {
  apiProfileId: '',
  modelName: '',
  temperature: 0.3,
  top_k: null,
}

function createProfileId(): string {
  return crypto.randomUUID()
}

export function createDefaultProfile(overrides?: Partial<ApiProfile>): ApiProfile {
  return {
    id: createProfileId(),
    name: '默认',
    base_url: defaultApiConfig.base_url,
    api_key: '',
    models: [defaultApiConfig.model],
    extra_body: {},
    ...overrides,
  }
}

function deserializeProfile(raw: StoredApiProfile): ApiProfile {
  return {
    id: raw.id,
    name: raw.name,
    base_url: normalizeBaseUrl(raw.base_url),
    api_key: decryptSecret(raw.api_key),
    models: raw.models?.length ? [...raw.models] : [defaultApiConfig.model],
    extra_body: normalizeExtraBody(raw.extra_body),
  }
}

function serializeProfile(profile: ApiProfile): StoredApiProfile {
  const extra = normalizeExtraBody(profile.extra_body)
  return {
    id: profile.id,
    name: profile.name,
    base_url: normalizeBaseUrl(profile.base_url),
    api_key: encryptSecret(profile.api_key),
    models: profile.models.filter(Boolean),
    ...(Object.keys(extra).length > 0 ? { extra_body: extra } : {}),
  }
}

function deserializeRegistry(raw: StoredApiProfileRegistry): ApiProfileRegistry {
  const profiles = raw.profiles.map(deserializeProfile)
  let needsResave = false
  for (const item of raw.profiles) {
    if (item.api_key && !isEncryptedSecret(item.api_key)) {
      needsResave = true
      break
    }
  }
  const registry = { profiles }
  if (needsResave) {
    saveApiProfileRegistry(registry)
  }
  return registry
}

function migrateLegacyApiConfig(): ApiProfileRegistry | null {
  try {
    const raw = localStorage.getItem(API_CONFIG_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as {
      base_url?: string
      api_key?: string
      model?: string
    }
    const legacy: ApiConfig = {
      ...defaultApiConfig,
      base_url: parsed.base_url ?? defaultApiConfig.base_url,
      api_key: decryptSecret(parsed.api_key ?? ''),
      model: parsed.model ?? defaultApiConfig.model,
      temperature: defaultApiConfig.temperature,
      top_k: defaultApiConfig.top_k,
    }
    const profile = createDefaultProfile({
      name: '默认',
      base_url: legacy.base_url,
      api_key: legacy.api_key,
      models: legacy.model ? [legacy.model] : [defaultApiConfig.model],
    })
    const registry = { profiles: [profile] }
    saveApiProfileRegistry(registry)
    localStorage.removeItem(API_CONFIG_STORAGE_KEY)
    return registry
  } catch {
    return null
  }
}

export function loadApiProfileRegistry(): ApiProfileRegistry {
  try {
    const raw = localStorage.getItem(API_PROFILES_STORAGE_KEY)
    if (!raw) {
      const migrated = migrateLegacyApiConfig()
      if (migrated) return migrated
      const registry = { profiles: [createDefaultProfile()] }
      saveApiProfileRegistry(registry)
      return registry
    }
    return deserializeRegistry(JSON.parse(raw) as StoredApiProfileRegistry)
  } catch {
    const registry = { profiles: [createDefaultProfile()] }
    saveApiProfileRegistry(registry)
    return registry
  }
}

export function saveApiProfileRegistry(registry: ApiProfileRegistry): void {
  const payload: StoredApiProfileRegistry = {
    profiles: registry.profiles.map(serializeProfile),
  }
  localStorage.setItem(API_PROFILES_STORAGE_KEY, JSON.stringify(payload))
}

export function clearApiProfileRegistry(): void {
  localStorage.removeItem(API_PROFILES_STORAGE_KEY)
  localStorage.removeItem(RUNTIME_STORAGE_KEYS.test)
  localStorage.removeItem(RUNTIME_STORAGE_KEYS.jailbreak)
}

export function hasSavedApiProfileRegistry(): boolean {
  return localStorage.getItem(API_PROFILES_STORAGE_KEY) !== null
}

export function getProfileById(
  registry: ApiProfileRegistry,
  id: string,
): ApiProfile | undefined {
  return registry.profiles.find((item) => item.id === id)
}

export function getFirstProfile(registry: ApiProfileRegistry): ApiProfile | null {
  return registry.profiles[0] ?? null
}

export function pickModelForProfile(profile: ApiProfile, preferred?: string): string {
  if (preferred && profile.models.includes(preferred)) {
    return preferred
  }
  return profile.models[0] ?? ''
}

export function normalizeRuntimeConfig(
  runtime: PageRuntimeConfig,
  registry: ApiProfileRegistry,
): PageRuntimeConfig {
  const first = getFirstProfile(registry)
  if (!first) {
    return { ...defaultRuntimeConfig }
  }
  const profile = getProfileById(registry, runtime.apiProfileId) ?? first
  const hasExplicitList = Array.isArray(runtime.modelNames)
  let effectiveNames: string[]
  if (hasExplicitList) {
    effectiveNames = runtime.modelNames!.filter((m) => profile.models.includes(m))
  } else {
    const sortedFirst =
      [...profile.models].sort((a, b) => a.localeCompare(b))[0] ??
      pickModelForProfile(profile, runtime.modelName)
    effectiveNames = sortedFirst ? [sortedFirst] : []
  }
  return {
    apiProfileId: profile.id,
    modelName: effectiveNames[0] ?? '',
    modelNames: effectiveNames,
    temperature: runtime.temperature ?? defaultRuntimeConfig.temperature,
    top_k: runtime.top_k ?? defaultRuntimeConfig.top_k,
  }
}

export function loadPageRuntime(scope: RuntimeScope): PageRuntimeConfig {
  const registry = loadApiProfileRegistry()
  try {
    const raw = localStorage.getItem(RUNTIME_STORAGE_KEYS[scope])
    if (!raw) {
      const first = getFirstProfile(registry)
      if (!first) return { ...defaultRuntimeConfig }
      return normalizeRuntimeConfig(
        {
          apiProfileId: first.id,
          modelName: first.models[0] ?? '',
          temperature: defaultRuntimeConfig.temperature,
          top_k: defaultRuntimeConfig.top_k,
        },
        registry,
      )
    }
    const parsed = JSON.parse(raw) as PageRuntimeConfig
    return normalizeRuntimeConfig(parsed, registry)
  } catch {
    const first = getFirstProfile(registry)
    if (!first) return { ...defaultRuntimeConfig }
    return normalizeRuntimeConfig(
      {
        apiProfileId: first.id,
        modelName: first.models[0] ?? '',
        temperature: defaultRuntimeConfig.temperature,
        top_k: defaultRuntimeConfig.top_k,
      },
      registry,
    )
  }
}

export function savePageRuntime(scope: RuntimeScope, runtime: PageRuntimeConfig): void {
  localStorage.setItem(RUNTIME_STORAGE_KEYS[scope], JSON.stringify(runtime))
}

export function resolveRuntimeRequest(
  registry: ApiProfileRegistry,
  runtime: PageRuntimeConfig,
  modelFallback = '',
): ResolvedRuntimeRequest | null {
  const normalized = normalizeRuntimeConfig(runtime, registry)
  const profile = getProfileById(registry, normalized.apiProfileId)
  if (!profile) return null
  const model = modelFallback.trim() || normalized.modelName
  if (!profile.base_url.trim() || !profile.api_key.trim() || !model.trim()) {
    return null
  }
  return {
    base_url: normalizeBaseUrl(profile.base_url),
    api_key: profile.api_key,
    model,
    temperature: normalized.temperature,
    top_k: normalized.top_k,
    extra_body: normalizeExtraBody(profile.extra_body),
  }
}

/** 翻译等模块 fallback：取第一个 Profile 的第一个 model */
export function resolveDefaultApiCredentials(): Pick<
  ResolvedRuntimeRequest,
  'base_url' | 'api_key' | 'model' | 'temperature'
> | null {
  const registry = loadApiProfileRegistry()
  const first = getFirstProfile(registry)
  if (!first) return null
  const model = first.models[0] ?? ''
  if (!first.base_url.trim() || !first.api_key.trim() || !model.trim()) {
    return null
  }
  return {
    base_url: normalizeBaseUrl(first.base_url),
    api_key: first.api_key,
    model,
    temperature: defaultRuntimeConfig.temperature,
  }
}
