import { ElMessage } from 'element-plus'
import type { MessageHandler, MessageOptions } from 'element-plus'

const SUCCESS_DURATION = 2000
const ERROR_DURATION = 3000

type MessageParams = string | MessageOptions | undefined

function withDuration(options: MessageParams, duration: number): MessageOptions {
  if (options == null) {
    return { duration }
  }
  if (typeof options === 'string') {
    return { message: options, duration }
  }
  return {
    ...options,
    duration: options.duration ?? duration,
  }
}

function patchMessageType(
  type: 'success' | 'warning' | 'info' | 'error',
  duration: number,
) {
  const invoke = ElMessage[type].bind(ElMessage) as (
    options?: MessageParams,
  ) => MessageHandler
  ElMessage[type] = ((options?: MessageParams) =>
    invoke(withDuration(options, duration))) as typeof ElMessage.success
}

/** 成功/提示 2s 自动关闭；错误 3s；悬停不暂停计时 */
export function setupElMessageBehavior() {
  patchMessageType('success', SUCCESS_DURATION)
  patchMessageType('warning', SUCCESS_DURATION)
  patchMessageType('info', SUCCESS_DURATION)
  patchMessageType('error', ERROR_DURATION)
}
