import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { runChatCompletion, type ChatCompletionResponse } from '../api'

export function useChatCompletionRun() {
  const running = ref(false)
  const lastResponse = ref<ChatCompletionResponse | null>(null)
  const rawContent = ref('')
  const reasoningContent = ref('')
  const reasoningExpanded = ref<string[]>([])

  async function execute(params: {
    requestConfig: {
      base_url: string
      api_key: string
      model: string
      temperature: number
      top_k: number | null
      extra_body?: Record<string, unknown> | null
    } | null
    systemPrompt: string
    userContent: string
    successMessage?: string
  }): Promise<boolean> {
    if (!params.requestConfig) {
      ElMessage.error('请先在「API 配置」页填写 API 配置并选择 model')
      return false
    }
    if (!params.systemPrompt.trim()) {
      ElMessage.error('System Prompt 为空')
      return false
    }
    if (!params.userContent.trim()) {
      ElMessage.error('请输入探针内容')
      return false
    }

    running.value = true
    lastResponse.value = null
    rawContent.value = ''
    reasoningContent.value = ''
    reasoningExpanded.value = []

    try {
      const resp = await runChatCompletion({
        base_url: params.requestConfig.base_url,
        api_key: params.requestConfig.api_key,
        model: params.requestConfig.model,
        temperature: params.requestConfig.temperature,
        top_k: params.requestConfig.top_k ?? null,
        extra_body: params.requestConfig.extra_body ?? undefined,
        system_prompt: params.systemPrompt,
        user_content: params.userContent,
      })
      lastResponse.value = resp
      rawContent.value = resp.raw_content || resp.error || resp.raw_text || ''
      reasoningContent.value = resp.reasoning_content || ''
      if (resp.status === 200) {
        ElMessage.success(params.successMessage ?? '请求完成')
        return true
      }
      ElMessage.error(`请求失败: HTTP ${resp.status}`)
      return false
    } catch (error) {
      ElMessage.error(error instanceof Error ? error.message : '请求异常')
      return false
    } finally {
      running.value = false
    }
  }

  return {
    running,
    lastResponse,
    rawContent,
    reasoningContent,
    reasoningExpanded,
    execute,
  }
}
