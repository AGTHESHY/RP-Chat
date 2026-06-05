/** 单模型测评基础等待时间（秒） */
export const CHAT_TIMEOUT_BASE_SECONDS = 120

/** 每增加一个被测模型追加的等待时间（秒） */
export const CHAT_TIMEOUT_PER_MODEL_SECONDS = 80

/** 上游 LLM 请求最长等待时间（秒） */
export const CHAT_TIMEOUT_MAX_SECONDS = 600

/**
 * 根据被测模型数量计算 chat completion 空闲超时（秒）。
 * 流式场景下指「连续无数据」的最长等待，非总时长；有 chunk 则重置计时。
 * 1 模型 120s，每多 1 模型 +80s，上限 600s。
 */
export function computeAdaptiveChatTimeout(modelCount: number): number {
  const count = Math.max(1, Math.floor(modelCount))
  return Math.min(
    CHAT_TIMEOUT_MAX_SECONDS,
    CHAT_TIMEOUT_BASE_SECONDS + (count - 1) * CHAT_TIMEOUT_PER_MODEL_SECONDS,
  )
}

/** 单模型测评基础 max_completion_tokens */
export const CHAT_MAX_TOKENS_BASE = 4096

/** 每增加一个被测模型追加的 max_completion_tokens */
export const CHAT_MAX_TOKENS_PER_MODEL = 1536

/** max_completion_tokens 上限 */
export const CHAT_MAX_TOKENS_CAP = 16384

/** 多模型测评 JSON 输出更长，按模型数放大 max_completion_tokens */
export function computeAdaptiveMaxCompletionTokens(modelCount: number): number {
  const count = Math.max(1, Math.floor(modelCount))
  return Math.min(
    CHAT_MAX_TOKENS_CAP,
    CHAT_MAX_TOKENS_BASE + (count - 1) * CHAT_MAX_TOKENS_PER_MODEL,
  )
}
