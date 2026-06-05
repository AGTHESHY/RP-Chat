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
