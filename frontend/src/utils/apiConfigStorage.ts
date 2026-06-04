
export const CHAT_COMPLETIONS_PATH = '/v1/chat/completions'

/** 补全 OpenAI 兼容 Chat Completions 路径 */
export function normalizeBaseUrl(url: string): string {
  const trimmed = url.trim().replace(/\/+$/, '')
  if (!trimmed) return trimmed

  const lower = trimmed.toLowerCase()
  if (lower.endsWith('/v1/chat/completions')) {
    return trimmed
  }
  if (lower.endsWith('/v1/chat/completion')) {
    return `${trimmed.slice(0, -'/completion'.length)}/completions`
  }
  if (lower.endsWith('/v1/chat')) {
    return `${trimmed}/completions`
  }
  if (lower.endsWith('/v1')) {
    return `${trimmed}/chat/completions`
  }
  return `${trimmed}${CHAT_COMPLETIONS_PATH}`
}

export function normalizeApiConfig(config: ApiConfig): ApiConfig {
  return {
    ...config,
    base_url: normalizeBaseUrl(config.base_url),
  }
}

export interface ApiConfig {
  base_url: string
  api_key: string
  model: string
  temperature: number
  top_k: number | null
}

export const API_CONFIG_STORAGE_KEY = 'rp-chat-api-config'

export const defaultApiConfig: ApiConfig = {
  base_url: 'http://32.194.212.226:3000/v1/chat/completions',
  api_key: '',
  model: 'deepseek-v4-pro-none',
  temperature: 0.3,
  top_k: null,
}
