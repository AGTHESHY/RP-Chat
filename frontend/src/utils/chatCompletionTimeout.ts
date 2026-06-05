/** 单模型测评基础等待时间（秒） */
export const CHAT_TIMEOUT_BASE_SECONDS = 120

/** 每增加一个被测模型追加的等待时间（秒） */
export const CHAT_TIMEOUT_PER_MODEL_SECONDS = 80

/** 上游 LLM 请求最长等待时间（秒） */
export const CHAT_TIMEOUT_MAX_SECONDS = 600

/**
 * 根据被测模型数量计算 chat completion 超时（秒）。
 * 1 模型 120s，每多 1 模型 +80s，上限 600s。
 */
export function computeAdaptiveChatTimeout(modelCount: number): number {
  const count = Math.max(1, Math.floor(modelCount))
  return Math.min(
    CHAT_TIMEOUT_MAX_SECONDS,
    CHAT_TIMEOUT_BASE_SECONDS + (count - 1) * CHAT_TIMEOUT_PER_MODEL_SECONDS,
  )
}
