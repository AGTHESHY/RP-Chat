<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  composePrompt,
  getChatQaConversation,
  getPromptTestResultByConversation,
  getRpHistoryDetail,
  getVersionPrompt,
  listChatQaConversations,
  listRpHistory,
  listVersions,
  runChatCompletion,
  savePromptTestResult,
  type ChatCompletionResponse,
  type PromptTestResultDetail,
  type ChatQaConversationSummary,
  type PromptLang,
  type PromptType,
  type RpHistoryDetail,
  type RpHistoryRunMeta,
  type RpHistorySummary,
} from '../api'
import { formatHistoryTime } from '../utils/format'
import ApiRuntimePicker from '../components/ApiRuntimePicker.vue'
import ResultPanel from '../components/ResultPanel.vue'
import { usePageRuntime } from '../composables/usePageRuntime'
import type { ResolvedRuntimeRequest } from '../utils/apiProfileStorage'
import {
  buildHistoryMergePayload,
  buildSegmentCompressPayload,
  getSegmentRoundRange,
  parseModelJson,
  promptTypeLabel,
  validateRoundRange,
  type SelectedConversation,
} from '../utils/conversationPayload'

const testRuntime = usePageRuntime('test')
const {
  runtime,
  registry,
  selectedModelNames,
  hasValidRuntime,
  setSelectedModels,
  resetToFirstModelSelection,
  syncWithRegistry,
  resolveRequestWithModelFallback,
} = testRuntime
const versionOptions = ref<string[]>(['v1', 'v2'])
const version = ref('v2')
const promptType = ref<PromptType>('segment_compress')
const lang = ref<PromptLang>('en')

const NSFW_STORAGE_KEY = 'rp-chat-include-nsfw'

function loadIncludeNsfw(): boolean {
  try {
    const raw = localStorage.getItem(NSFW_STORAGE_KEY)
    if (raw === null) return true
    return raw === 'true'
  } catch {
    return true
  }
}

const includeNsfw = ref(loadIncludeNsfw())
const promptSfw = ref('')
const promptNsfw = ref('')

const conversationOptions = ref<ChatQaConversationSummary[]>([])
const selectedConversationKey = ref<string>('')
const selectedConversation = ref<SelectedConversation | null>(null)
const roundRange = ref({ start: 1, end: 10 })
const running = ref(false)
const lastResponse = ref<ChatCompletionResponse | null>(null)
const rawContent = ref('')
const reasoningContent = ref('')
const reasoningExpanded = ref<string[]>([])

interface TestStepResult {
  promptType: PromptType
  response: ChatCompletionResponse
  rawContent: string
  reasoningContent: string
}

interface ModelRunBundle {
  model: string
  steps: TestStepResult[]
  error?: string
}

const stepResults = ref<TestStepResult[]>([])
const modelRunBundles = ref<ModelRunBundle[]>([])

const rpHistoryOptions = ref<RpHistorySummary[]>([])
const selectedRpHistoryKey = ref('')

const selectedRpHistorySummary = computed(
  () =>
    rpHistoryOptions.value.find((item) => item.history_key === selectedRpHistoryKey.value) ??
    null,
)

const rpHistoryDetail = ref<RpHistoryDetail | null>(null)

const rpHistoryTypeHint = computed(() => {
  if (!selectedRpHistoryKey.value) return ''
  const summary = selectedRpHistorySummary.value
  if (!summary) return ''
  if (summary.has_compress && summary.has_merge) {
    return '该历史包含Compress和Merge'
  }
  if (summary.has_compress) return '该历史含 Compress'
  if (summary.has_merge) return '该历史含 Merge'
  return ''
})

const systemPrompt = computed(() =>
  composePrompt(promptSfw.value, promptNsfw.value, includeNsfw.value),
)

const roundRangeHint = computed(() => {
  if (!selectedConversationMaxRounds.value) return ''
  return `共 ${selectedConversationMaxRounds.value} 轮，每轮为一问一答`
})

const selectedConversationMaxRounds = computed(() => {
  if (!selectedConversationKey.value) return 0
  const row = conversationOptions.value.find(
    (item) => item.conversation_key === selectedConversationKey.value,
  )
  return row?.message_count ?? 0
})

function conversationOptionLabel(row: ChatQaConversationSummary): string {
  return `${row.role_name} · 用户 ${row.user_id} · 角色 ${row.role_id} · ${row.message_count} 轮`
}

function applyConversation(row: ChatQaConversationSummary) {
  selectedConversationKey.value = row.conversation_key
  selectedConversation.value = {
    conversation_key: row.conversation_key,
    user_id: row.user_id,
    role_id: row.role_id,
    app_name: row.app_name,
    role_name: row.role_name,
  }
  roundRange.value = getSegmentRoundRange(row.message_count)
}

async function loadConversationOptions() {
  conversationOptions.value = await listChatQaConversations()
  if (conversationOptions.value.length === 0) {
    selectedConversationKey.value = ''
    selectedConversation.value = null
    return
  }
  const currentKey = selectedConversationKey.value
  const matched =
    currentKey && conversationOptions.value.find((item) => item.conversation_key === currentKey)
  if (matched) {
    applyConversation(matched)
    return
  }
  applyConversation(conversationOptions.value[0])
}

watch(selectedConversationKey, (key) => {
  if (!key) {
    selectedConversation.value = null
    return
  }
  const row = conversationOptions.value.find((item) => item.conversation_key === key)
  if (row) {
    applyConversation(row)
  }
})

watch(includeNsfw, (value) => {
  localStorage.setItem(NSFW_STORAGE_KEY, String(value))
})

async function buildUserPayload(
  type: PromptType,
  options?: { compressExpected?: Record<string, unknown> },
): Promise<Record<string, unknown>> {
  const conv = selectedConversation.value
  if (!conv) {
    throw new Error('请先选择测试用例')
  }

  const detail = await getChatQaConversation({
    user_id: conv.user_id,
    role_id: conv.role_id,
    app_name: conv.app_name,
  })
  const range = validateRoundRange(
    roundRange.value.start,
    roundRange.value.end,
    detail.messages.length,
  )

  if (type === 'segment_compress') {
    return buildSegmentCompressPayload(
      detail.messages,
      conv,
      range.start,
      range.end,
    )
  }

  let compressExpected = options?.compressExpected
  if (!compressExpected) {
    try {
      const saved = await getPromptTestResultByConversation({
        user_id: conv.user_id,
        role_id: conv.role_id,
        app_name: conv.app_name,
        prompt_type: 'segment_compress',
      })
      compressExpected = saved.expected_result
    } catch {
      throw new Error('History 合并需先对该会话运行 Segment 压缩测试')
    }
  }

  let oldHistoryMemory = ''
  try {
    const savedMerge = await getPromptTestResultByConversation({
      user_id: conv.user_id,
      role_id: conv.role_id,
      app_name: conv.app_name,
      prompt_type: 'history_merge',
    })
    oldHistoryMemory = String(savedMerge.expected_result.history_memory ?? '')
  } catch {
    oldHistoryMemory = ''
  }

  return buildHistoryMergePayload(
    compressExpected,
    range.start,
    range.end,
    oldHistoryMemory,
  )
}

async function loadPromptParts(type: PromptType) {
  const data = await getVersionPrompt(version.value, type, lang.value)
  return {
    sfw: data.content_sfw,
    nsfw: data.content_nsfw,
    system: composePrompt(data.content_sfw, data.content_nsfw, includeNsfw.value),
  }
}

async function executeTestStep(
  type: PromptType,
  userPayload: Record<string, unknown>,
  systemPromptText: string,
  requestConfig: ResolvedRuntimeRequest,
): Promise<TestStepResult> {
  if (!systemPromptText.trim()) {
    throw new Error(`${promptTypeLabel(type)} 的 System Prompt 未加载`)
  }

  const resp = await runChatCompletion({
    base_url: requestConfig.base_url,
    api_key: requestConfig.api_key,
    model: requestConfig.model,
    temperature: requestConfig.temperature,
    top_k: requestConfig.top_k ?? null,
    extra_body: requestConfig.extra_body,
    system_prompt: systemPromptText,
    user_content: JSON.stringify(userPayload, null, 2),
  })

  const stepRaw = resp.raw_content || resp.error || resp.raw_text || ''
  return {
    promptType: type,
    response: resp,
    rawContent: stepRaw,
    reasoningContent: resp.reasoning_content || '',
  }
}

function initialBatchRunGroupId(): number | undefined {
  if (!selectedRpHistoryKey.value || !rpHistoryDetail.value) {
    return undefined
  }
  return rpHistoryDetail.value.run_group_id
}

async function saveStepResult(
  type: PromptType,
  parsed: Record<string, unknown>,
  requestConfig: ResolvedRuntimeRequest,
  runGroupId?: number,
): Promise<PromptTestResultDetail | null> {
  const conv = selectedConversation.value
  if (!conv) return null
  return savePromptTestResult({
    user_id: conv.user_id,
    role_id: conv.role_id,
    app_name: conv.app_name,
    role_name: conv.role_name,
    prompt_type: type,
    expected_result: parsed,
    round_start: roundRange.value.start,
    round_end: roundRange.value.end,
    prompt_version: version.value,
    model: requestConfig.model,
    top_k: requestConfig.top_k ?? null,
    temperature: requestConfig.temperature,
    ...(runGroupId != null ? { run_group_id: runGroupId } : {}),
  })
}

function applyStepToDisplay(step: TestStepResult) {
  lastResponse.value = step.response
  rawContent.value = step.rawContent
  reasoningContent.value = step.reasoningContent
}

function rpHistoryOptionLabel(row: RpHistorySummary): string {
  const flags = [
    row.has_compress ? 'C' : '',
    row.has_merge ? 'M' : '',
  ]
    .filter(Boolean)
    .join('')
  const time = row.latest_updated_at ? formatHistoryTime(row.latest_updated_at) : ''
  return [
    row.role_name,
    `${row.round_start}-${row.round_end}轮`,
    row.prompt_version ? `SP:${row.prompt_version}` : null,
    flags || null,
    row.model_count > 0 ? `${row.model_count}模型` : null,
    time || null,
  ]
    .filter(Boolean)
    .join(' · ')
}

function compressForModel(model: string): Record<string, unknown> | undefined {
  if (!selectedRpHistoryKey.value || !rpHistoryDetail.value) return undefined
  const run = rpHistoryDetail.value.model_runs?.find((item) => item.model === model)
  return run?.compress ?? undefined
}

function pickRunMetaForPromptType(
  detail: RpHistoryDetail,
  type: PromptType,
): RpHistoryRunMeta | null | undefined {
  const runs = detail.model_runs ?? []
  for (const run of runs) {
    if (type === 'history_merge' && run.merge_run) return run.merge_run
    if (type === 'segment_compress' && run.compress_run) return run.compress_run
  }
  return runs[0]?.compress_run ?? runs[0]?.merge_run
}

function applyRunMeta(run: RpHistoryRunMeta | null | undefined) {
  if (!run) return
  if (run.prompt_version && versionOptions.value.includes(run.prompt_version)) {
    version.value = run.prompt_version
  }
  runtime.value.temperature = run.temperature
  runtime.value.top_k = run.top_k
}

async function syncRpHistorySelection(key: string) {
  if (!key) {
    rpHistoryDetail.value = null
    resetToFirstModelSelection()
    return
  }
  const summary = selectedRpHistorySummary.value
  if (!summary) return
  try {
    const detail = await getRpHistoryDetail({
      user_id: summary.user_id,
      role_id: summary.role_id,
      app_name: summary.app_name,
      run_group_id: summary.run_group_id,
    })
    rpHistoryDetail.value = detail
    await applyRpHistoryContext(detail)
    applyHistoryModelSelection(detail)
    applyRunMeta(pickRunMetaForPromptType(detail, promptType.value))
    await loadSystemPrompt()
  } catch (error) {
    rpHistoryDetail.value = null
    ElMessage.error(error instanceof Error ? error.message : '加载 RP 历史失败')
  }
}

function applyHistoryModelSelection(detail: RpHistoryDetail) {
  const historyModels = (detail.model_runs ?? [])
    .map((run) => run.model.trim())
    .filter(Boolean)

  if (historyModels.length === 0) return

  let bestProfileId = runtime.value.apiProfileId
  let bestValid: string[] = []
  for (const profile of registry.value.profiles) {
    const valid = historyModels.filter((model) => profile.models.includes(model))
    if (valid.length > bestValid.length) {
      bestValid = valid
      bestProfileId = profile.id
    }
  }

  if (bestValid.length === 0) {
    ElMessage.warning('该历史记录中的模型在当前 API 配置中均不可用')
    return
  }

  runtime.value.apiProfileId = bestProfileId
  setSelectedModels(bestValid)
}

async function applyRpHistoryContext(detail: RpHistoryDetail) {
  const matched = conversationOptions.value.find(
    (item) => item.conversation_key === detail.conversation_key,
  )
  if (matched) {
    applyConversation(matched)
  } else {
    selectedConversationKey.value = detail.conversation_key
    selectedConversation.value = {
      conversation_key: detail.conversation_key,
      user_id: detail.user_id,
      role_id: detail.role_id,
      app_name: detail.app_name,
      role_name: detail.role_name,
    }
  }
  roundRange.value = {
    start: detail.round_start,
    end: detail.round_end,
  }
}

interface ExecuteRunOptions {
  mode: PromptType
  mergeCompressExpected?: Record<string, unknown>
}

async function executeRun(options: ExecuteRunOptions) {
  const mode = options.mode

  if (!selectedConversation.value) {
    ElMessage.error('请先选择测试用例')
    return
  }

  const models = selectedModelNames.value
  if (models.length === 0) {
    ElMessage.error('请至少选择一个模型')
    return
  }

  running.value = true
  lastResponse.value = null
  rawContent.value = ''
  reasoningContent.value = ''
  reasoningExpanded.value = []
  stepResults.value = []
  modelRunBundles.value = []

  try {
    const type = mode

    let systemText = systemPrompt.value
    if (type === 'history_merge') {
      const mergeParts = await loadPromptParts('history_merge')
      systemText = mergeParts.system
    }
    if (!systemText.trim()) {
      ElMessage.error('System Prompt 未加载')
      return
    }

    const settled = await Promise.allSettled(
      models.map(async (model) => {
        let parsed: Record<string, unknown>
        try {
          parsed = await buildUserPayload(type, {
            compressExpected:
              options.mergeCompressExpected ?? compressForModel(model),
          })
        } catch (error) {
          throw error instanceof Error ? error : new Error('构建测试输入失败')
        }
        const requestConfig = resolveRequestWithModelFallback(model)
        if (!requestConfig) {
          throw new Error(`模型 ${model} 配置无效`)
        }
        const step = await executeTestStep(type, parsed, systemText, requestConfig)
        return { model, step, requestConfig }
      }),
    )

    const bundles: ModelRunBundle[] = []
    let successCount = 0
    let savedCount = 0
    let batchRunGroupId = initialBatchRunGroupId()

    for (let i = 0; i < settled.length; i++) {
      const outcome = settled[i]
      const model = models[i]
      if (outcome.status === 'rejected') {
        bundles.push({
          model,
          steps: [],
          error: outcome.reason instanceof Error ? outcome.reason.message : '请求失败',
        })
        continue
      }
      const { step, requestConfig } = outcome.value
      bundles.push({ model, steps: [step] })
      if (step.response.status !== 200) continue
      successCount += 1
      const parsedResult = parseModelJson(step.rawContent)
      if (!parsedResult) continue
      try {
        const saved = await saveStepResult(type, parsedResult, requestConfig, batchRunGroupId)
        if (saved?.run_group_id != null && batchRunGroupId == null) {
          batchRunGroupId = saved.run_group_id
        }
        savedCount += 1
      } catch {
        /* 单条保存失败，继续其余模型 */
      }
    }

    modelRunBundles.value = bundles
    const firstOk = bundles.find((b) => b.steps.length > 0)
    if (firstOk?.steps[0]) {
      stepResults.value = firstOk.steps
      applyStepToDisplay(firstOk.steps[0])
    }

    if (models.length === 1) {
      const b = bundles[0]
      if (b?.error) {
        ElMessage.error(b.error)
      } else if (b?.steps[0]?.response.status === 200) {
        ElMessage.success(savedCount > 0 ? '请求成功，已保存历史 RP 效果' : '请求成功')
      } else if (b?.steps[0]) {
        ElMessage.error(`请求失败: HTTP ${b.steps[0].response.status}`)
      }
    } else {
      ElMessage.info(
        `并行完成 ${models.length} 个模型：成功 ${successCount}，已保存 ${savedCount}`,
      )
    }

    if (savedCount > 0) {
      await loadRpHistoryOptions()
      if (selectedRpHistoryKey.value) {
        await syncRpHistorySelection(selectedRpHistoryKey.value)
      }
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '请求异常')
  } finally {
    running.value = false
  }
}

async function runTest() {
  if (selectedRpHistoryKey.value && !rpHistoryDetail.value) {
    await syncRpHistorySelection(selectedRpHistoryKey.value)
  }

  if (promptType.value === 'history_merge') {
    const hasCompressFromHistory = Boolean(rpHistoryDetail.value?.compress)
    if (!hasCompressFromHistory) {
      try {
        await getPromptTestResultByConversation({
          user_id: selectedConversation.value!.user_id,
          role_id: selectedConversation.value!.role_id,
          app_name: selectedConversation.value!.app_name,
          prompt_type: 'segment_compress',
        })
      } catch {
        ElMessage.error(
          selectedRpHistoryKey.value
            ? '所选历史无 Compress，无法 Merge'
            : '尚无 Compress 结果，请先运行 Segment 压缩',
        )
        return
      }
    }
  }
  await executeRun({ mode: promptType.value })
}

async function loadRpHistoryOptions() {
  try {
    rpHistoryOptions.value = await listRpHistory()
  } catch {
    rpHistoryOptions.value = []
  }
}

watch([version, promptType, lang], async () => {
  await loadSystemPrompt()
})

watch(promptType, () => {
  stepResults.value = []
  if (!selectedRpHistoryKey.value || !rpHistoryDetail.value) return
  applyRunMeta(pickRunMetaForPromptType(rpHistoryDetail.value, promptType.value))
  void loadSystemPrompt()
})

watch(selectedRpHistoryKey, (key) => {
  void syncRpHistorySelection(key)
})

onMounted(async () => {
  syncWithRegistry()
  await Promise.all([
    loadConversationOptions(),
    loadVersionOptions(),
    loadRpHistoryOptions(),
  ])
  if (!selectedRpHistoryKey.value) {
    resetToFirstModelSelection()
  }
  await loadSystemPrompt()
})

async function loadSystemPrompt() {
  const data = await getVersionPrompt(version.value, promptType.value, lang.value)
  promptSfw.value = data.content_sfw
  promptNsfw.value = data.content_nsfw
}

async function loadVersionOptions() {
  const data = await listVersions()
  const options = [...data.baselines]
  for (const item of data.custom) {
    if (!options.includes(item.version)) {
      options.push(item.version)
    }
  }
  versionOptions.value = options
  if (!options.includes(version.value)) {
    version.value = options.includes('v2') ? 'v2' : options[0]
  }
}
</script>

<template>
  <div class="test-page">
    <el-row :gutter="16" class="main-row">
      <el-col :span="12" class="main-col">
        <el-card shadow="never" class="input-card">
          <template #header>
            <div class="panel-header">
              <span class="panel-title">Prompt 与输入</span>
              <ApiRuntimePicker scope="test" multi-select />
            </div>
          </template>

          <div class="input-card-body">
            <el-form label-width="100px" class="input-form">
            <el-form-item label="测试用例">
              <el-select
                v-model="selectedConversationKey"
                placeholder="选择测试用例"
                style="width: 100%"
                filterable
                :disabled="conversationOptions.length === 0"
              >
                <el-option
                  v-for="item in conversationOptions"
                  :key="item.conversation_key"
                  :label="conversationOptionLabel(item)"
                  :value="item.conversation_key"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="测试轮次">
              <div class="round-range-row">
                <span class="round-label">第</span>
                <el-input-number
                  v-model="roundRange.start"
                  :min="1"
                  :max="roundRange.end"
                  :disabled="!selectedConversation"
                  controls-position="right"
                />
                <span class="round-label">到第</span>
                <el-input-number
                  v-model="roundRange.end"
                  :min="roundRange.start"
                  :max="selectedConversationMaxRounds || 1"
                  :disabled="!selectedConversation"
                  controls-position="right"
                />
                <span class="round-label">轮</span>
              </div>
              <div v-if="roundRangeHint" class="hint block-hint">{{ roundRangeHint }}</div>
            </el-form-item>
            <el-form-item label="SP 版本">
              <div class="sp-version-row">
                <el-select v-model="version" placeholder="SP 版本" class="sp-version-select">
                  <el-option
                    v-for="item in versionOptions"
                    :key="item"
                    :label="item"
                    :value="item"
                  />
                </el-select>
                <el-select
                  v-model="selectedRpHistoryKey"
                  placeholder="重跑/补 Merge 时选择历史；不选则每次新增一条记录"
                  clearable
                  filterable
                  class="rp-history-select"
                  :class="{ 'rp-history-select--active': !!selectedRpHistoryKey }"
                  :disabled="rpHistoryOptions.length === 0"
                >
                  <el-option
                    v-for="item in rpHistoryOptions"
                    :key="item.history_key"
                    :label="rpHistoryOptionLabel(item)"
                    :value="item.history_key"
                  />
                </el-select>
              </div>
              <div v-if="rpHistoryOptions.length === 0" class="hint block-hint">
                暂无历史 RP 效果，请先运行测试
              </div>
            </el-form-item>
            <el-form-item label="类型">
              <div class="prompt-type-row">
                <el-radio-group v-model="promptType">
                  <el-radio-button label="segment_compress" value="segment_compress">
                    Segment 压缩
                  </el-radio-button>
                  <el-radio-button label="history_merge" value="history_merge">
                    History 合并
                  </el-radio-button>
                </el-radio-group>
                <span v-if="rpHistoryTypeHint" class="hint type-hint">{{ rpHistoryTypeHint }}</span>
              </div>
            </el-form-item>
            <el-form-item label="语言">
              <el-radio-group v-model="lang">
                <el-radio-button label="zh" value="zh">中文</el-radio-button>
                <el-radio-button label="en" value="en">English</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="temperature">
              <el-input-number v-model="runtime.temperature" :min="0" :max="2" :step="0.1" />
            </el-form-item>
            <el-form-item label="top_k">
              <el-input-number v-model="runtime.top_k" :min="1" :max="100" :step="1" />
              <span class="hint">留空则不传</span>
            </el-form-item>
            <el-form-item label="NSFW 段落" class="nsfw-row">
              <div class="nsfw-row-content">
                <div class="nsfw-controls">
                  <el-switch
                    v-model="includeNsfw"
                    active-text="开启"
                    inactive-text="关闭"
                  />
                  <span class="hint">关闭时最终 SP 不含 NSFW 规则，占位符会被移除</span>
                </div>
                <el-button
                  type="primary"
                  :loading="running"
                  :disabled="!hasValidRuntime"
                  @click="runTest"
                >
                  运行测试
                </el-button>
              </div>
            </el-form-item>
            </el-form>

            <div class="prompt-preview">
              <div class="preview-header">
                <span>System Prompt 预览（{{ includeNsfw ? 'SFW + NSFW' : '仅 SFW' }}）</span>
                <span class="preview-meta">{{ systemPrompt.length }} 字符</span>
              </div>
              <el-scrollbar class="preview-scroll">
                <pre class="prompt-pre preview-text">{{ systemPrompt }}</pre>
              </el-scrollbar>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12" class="main-col">
        <el-card shadow="never" class="result-card">
          <template #header>
            <span>返回结果</span>
          </template>

          <div class="run-result-body">
          <template v-if="modelRunBundles.length > 1">
            <div
              v-for="(bundle, index) in modelRunBundles"
              :key="bundle.model"
              class="model-run-block"
            >
              <h4 class="step-title">模型 · {{ bundle.model }}</h4>
              <p v-if="bundle.error" class="model-run-error">{{ bundle.error }}</p>
              <template v-else-if="bundle.steps[0]">
                <div class="usage">
                  <el-tag>HTTP {{ bundle.steps[0].response.status }}</el-tag>
                  <span v-if="bundle.steps[0].response.usage">
                    prompt: {{ bundle.steps[0].response.usage.prompt_tokens ?? 'N/A' }} |
                    completion: {{ bundle.steps[0].response.usage.completion_tokens ?? 'N/A' }} |
                    total: {{ bundle.steps[0].response.usage.total_tokens ?? 'N/A' }}
                  </span>
                </div>
                <ResultPanel
                  v-if="bundle.steps[0].rawContent"
                  :content="bundle.steps[0].rawContent"
                  :prompt-type="bundle.steps[0].promptType"
                />
              </template>
              <el-divider v-if="index < modelRunBundles.length - 1" />
            </div>
          </template>
          <template v-else-if="stepResults.length > 1">
            <div v-for="(step, index) in stepResults" :key="step.promptType" class="step-block">
              <h4 class="step-title">{{ promptTypeLabel(step.promptType) }}</h4>
              <div class="usage">
                <el-tag>HTTP {{ step.response.status }}</el-tag>
                <span v-if="step.response.usage">
                  prompt: {{ step.response.usage.prompt_tokens ?? 'N/A' }} |
                  completion: {{ step.response.usage.completion_tokens ?? 'N/A' }} |
                  total: {{ step.response.usage.total_tokens ?? 'N/A' }}
                </span>
              </div>
              <ResultPanel v-if="step.rawContent" :content="step.rawContent" :prompt-type="step.promptType" />
              <el-divider v-if="index < stepResults.length - 1" />
            </div>
          </template>
          <template v-else>
            <div v-if="lastResponse" class="usage">
              <el-tag>HTTP {{ lastResponse.status }}</el-tag>
              <span v-if="lastResponse.usage">
                prompt: {{ lastResponse.usage.prompt_tokens ?? 'N/A' }} |
                completion: {{ lastResponse.usage.completion_tokens ?? 'N/A' }} |
                total: {{ lastResponse.usage.total_tokens ?? 'N/A' }}
              </span>
              <span v-if="lastResponse.finish_reason">finish: {{ lastResponse.finish_reason }}</span>
            </div>

            <el-collapse v-if="reasoningContent" v-model="reasoningExpanded" class="reasoning-collapse">
              <el-collapse-item name="reasoning">
                <template #title>
                  <span>思考内容 (reasoning_content)</span>
                  <el-tag size="small" type="info" class="reasoning-tag">{{ reasoningContent.length }} 字符</el-tag>
                </template>
                <el-scrollbar max-height="280px">
                  <pre class="prompt-pre">{{ reasoningContent }}</pre>
                </el-scrollbar>
              </el-collapse-item>
            </el-collapse>

            <ResultPanel v-if="rawContent" :content="rawContent" :prompt-type="promptType" />
          </template>
          <el-empty
            v-if="!lastResponse && stepResults.length === 0 && modelRunBundles.length === 0"
            description="运行测试后在此查看结果"
            :image-size="72"
          />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.test-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.main-row {
  flex: 1;
  min-height: 0;
  align-items: stretch;
}

.main-col {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.input-card,
.result-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.input-card :deep(.el-card__body),
.result-card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.input-card-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.input-form {
  flex-shrink: 0;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: nowrap;
}

.panel-title {
  flex-shrink: 0;
  white-space: nowrap;
}

.hint {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}

.block-hint {
  margin-left: 0;
  margin-top: 6px;
}

.round-range-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.round-label {
  font-size: 14px;
  color: #606266;
}

.sp-version-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.sp-version-select {
  width: 100px;
  flex-shrink: 0;
}

.rp-history-select {
  flex: 1;
  min-width: 0;
  max-width: 100%;
}

.rp-history-select :deep(.el-select__wrapper) {
  font-size: 12px;
  line-height: 1.35;
  min-height: 28px;
}

.rp-history-select :deep(.el-select__placeholder) {
  font-size: 11px;
  line-height: 1.35;
  color: #a8abb2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rp-history-select--active :deep(.el-select__wrapper) {
  font-size: 14px;
  border-color: #409eff;
  box-shadow: 0 0 0 1px #409eff inset;
}

.rp-history-select--active :deep(.el-select__selected-item) {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.prompt-type-row {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 10px;
}

.type-hint {
  margin: 0;
  white-space: nowrap;
  flex-shrink: 0;
}

.nsfw-row :deep(.el-form-item__content) {
  flex: 1;
}

.nsfw-row-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 12px;
}

.nsfw-controls {
  display: flex;
  align-items: center;
}

.prompt-preview {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
}

.preview-header {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
  font-size: 13px;
  font-weight: 500;
}

.preview-meta {
  font-size: 12px;
  font-weight: 400;
  color: #909399;
}

.preview-scroll {
  flex: 1;
  min-height: 0;
}

.preview-scroll :deep(.el-scrollbar) {
  height: 100%;
}

.preview-scroll :deep(.el-scrollbar__wrap) {
  overflow-x: hidden;
}

.preview-text {
  margin: 0;
  padding: 12px;
  background: #fff;
}

.result-card {
  min-height: 0;
}

.usage {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  font-size: 13px;
  color: #606266;
}

.step-block {
  margin-bottom: 8px;
}

.step-title {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.model-run-block {
  margin-bottom: 8px;
}

.model-run-error {
  margin: 0 0 12px;
  font-size: 13px;
  color: #f56c6c;
}

.reasoning-collapse {
  margin-bottom: 16px;
  border: none;
}

.reasoning-collapse :deep(.el-collapse-item__header) {
  font-size: 14px;
  font-weight: 500;
  border-bottom: 1px solid #ebeef5;
}

.run-result-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.reasoning-tag {
  margin-left: 8px;
}
</style>
