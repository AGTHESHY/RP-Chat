import { resolveDefaultApiCredentials } from './apiProfileStorage'
import { normalizeBaseUrl, type ApiConfig } from './apiConfigStorage'
import { decryptSecret, encryptSecret, isEncryptedSecret } from './secretStorage'

export const TRANSLATE_CONFIG_STORAGE_KEY = 'rp-chat-translate-config'

export interface TranslateConfig {
  base_url: string
  api_key: string
  model: string
  temperature: number
}

interface StoredTranslateConfig {
  base_url: string
  api_key: string
  model: string
  temperature: number
}

export const defaultTranslateConfig: TranslateConfig = {
  base_url: '',
  api_key: '',
  model: '',
  temperature: 0.3,
}

function hasTranslateFields(config: TranslateConfig): boolean {
  return Boolean(config.base_url.trim() && config.api_key.trim() && config.model.trim())
}

function deserializeStoredConfig(raw: StoredTranslateConfig): TranslateConfig {
  return {
    ...defaultTranslateConfig,
    ...raw,
    api_key: decryptSecret(raw.api_key),
  }
}

function serializeConfig(config: TranslateConfig): StoredTranslateConfig {
  return {
    base_url: config.base_url,
    api_key: encryptSecret(config.api_key),
    model: config.model,
    temperature: config.temperature,
  }
}

export function loadTranslateConfig(): TranslateConfig {
  try {
    const raw = localStorage.getItem(TRANSLATE_CONFIG_STORAGE_KEY)
    if (!raw) return { ...defaultTranslateConfig }
    const parsed = JSON.parse(raw) as StoredTranslateConfig
    const config = deserializeStoredConfig(parsed)
    if (parsed.api_key && !isEncryptedSecret(parsed.api_key)) {
      saveTranslateConfig(config)
    }
    return config
  } catch {
    return { ...defaultTranslateConfig }
  }
}

export function saveTranslateConfig(config: TranslateConfig): void {
  localStorage.setItem(TRANSLATE_CONFIG_STORAGE_KEY, JSON.stringify(serializeConfig(config)))
}

export function clearTranslateConfig(): void {
  localStorage.removeItem(TRANSLATE_CONFIG_STORAGE_KEY)
}

export function hasSavedTranslateConfig(): boolean {
  return localStorage.getItem(TRANSLATE_CONFIG_STORAGE_KEY) !== null
}

/** 未配置翻译 API 时 fallback 到 API 配置页第一个 Profile */
export function resolveTranslateConfig(): Pick<
  ApiConfig,
  'base_url' | 'api_key' | 'model' | 'temperature'
> {
  const translate = loadTranslateConfig()
  if (hasTranslateFields(translate)) {
    return {
      base_url: normalizeBaseUrl(translate.base_url),
      api_key: translate.api_key,
      model: translate.model,
      temperature: translate.temperature,
    }
  }
  const fallback = resolveDefaultApiCredentials()
  if (fallback) {
    return fallback
  }
  return {
    base_url: '',
    api_key: '',
    model: '',
    temperature: 0.3,
  }
}
