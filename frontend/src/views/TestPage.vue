<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getRpHistoryDetail,
  listChatQaConversations,
  listRpCompressResults,
  listRpMergeResults,
  listRpHistory,
  listVersions,
  type ChatCompletionResponse,
  type RpTestJobCreateBody,
  type ChatQaConversationSummary,
  type PromptLang,
  type PromptType,
  type RpCompressSegmentDetail,
  type RpMergeResultDetail,
  type RpHistoryDetail,
  type RpHistoryRunMeta,
  type RpHistorySummary,
} from '../api'
import { formatHistoryTime } from '../utils/format'
import ApiRuntimePicker from '../components/ApiRuntimePicker.vue'
import ResultPanel from '../components/ResultPanel.vue'
import { usePageRuntime } from '../composables/usePageRuntime'
import {
  getSegmentRoundRange,
  maxNextSegmentIndex,
  mergeableSegmentsFromRecords,
  pickConsecutiveSegments,
  promptTypeLabel,
  type MergeableSegment,
  type SelectedConversation,
} from '../utils/conversationPayload'
import {
  formatPipelineCycleLines,
  planMemoryPipeline,
  pipelinePlanSummary,
  type PipelinePlan,
} from '../utils/memoryPipeline'
import {
  attachRpTestJobRunner,
  recoverRpTestJob,
  startRpTestJob,
  subscribeRpTestJob,
  type RpTestJobSnapshot,
} from '../services/rpTestJobRunner'

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
const testMode = ref<'pipeline' | 'single'>('pipeline')
const promptType = ref<PromptType>('segment_compress')
const lang = ref<PromptLang>('en')

const conversationOptions = ref<ChatQaConversationSummary[]>([])
const selectedConversationKey = ref<string>('')
const selectedConversation = ref<SelectedConversation | null>(null)
const roundRange = ref({ start: 1, end: 10 })
const selectedSegmentIndex = ref(1)
const loadedCompressSegments = ref<RpCompressSegmentDetail[]>([])
const loadedMergeResults = ref<RpMergeResultDetail[]>([])

interface SavedPreviewPanel {
  title: string
  meta: string
  content: string
  type: PromptType
}
const mergeSegmentCount = ref(1)
const mergeSegmentEndIndex = ref(1)
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
  stepLabel?: string
}

interface ModelRunBundle {
  model: string
  steps: TestStepResult[]
  error?: string
}

const stepResults = ref<TestStepResult[]>([])
const modelRunBundles = ref<ModelRunBundle[]>([])
const pipelineForcedTailWarning = ref(false)
const jobSnapshot = ref<RpTestJobSnapshot | null>(null)

const jobProgressHint = computed(() => {
  const snap = jobSnapshot.value
  if (!snap || snap.phase !== 'running') return ''
  if (snap.progressTotal > 0) {
    return `测试中 ${snap.progressStep}/${snap.progressTotal} 步 · 可切换页面`
  }
  return '测试中 · 可切换页面'
})

function applyJobSnapshot(snap: RpTestJobSnapshot) {
  jobSnapshot.value = snap
  running.value = snap.phase === 'running'
  modelRunBundles.value = snap.modelBundles
  stepResults.value = snap.stepResults
  lastResponse.value = snap.lastResponse
  rawContent.value = snap.rawContent
  reasoningContent.value = snap.reasoningContent
  if (snap.phase === 'running' || snap.phase === 'done') {
    pipelineForcedTailWarning.value = snap.pipelineForcedTailWarning
  }
}

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

const roundRangeHint = computed(() => {
  if (!selectedConversationMaxRounds.value) return ''
  return `共 ${selectedConversationMaxRounds.value} 轮，每轮为一问一答`
})

const pipelinePlan = computed<PipelinePlan | null>(() => {
  if (testMode.value !== 'pipeline') return null
  if (!roundRange.value.start || !roundRange.value.end) return null
  if (roundRange.value.start > roundRange.value.end) return null
  return planMemoryPipeline(roundRange.value.start, roundRange.value.end)
})

const pipelinePreviewSummary = computed(() => {
  if (!pipelinePlan.value || pipelinePlan.value.segments.length === 0) {
    return '当前轮次范围内没有可切分的 Segment'
  }
  return pipelinePlanSummary(pipelinePlan.value)
})

const pipelineCycleLines = computed(() => {
  if (!pipelinePlan.value || pipelinePlan.value.segments.length === 0) return []
  return formatPipelineCycleLines(pipelinePlan.value)
})

const availableMergeSegments = computed<MergeableSegment[]>(() => {
  try {
    return mergeableSegmentsFromRecords(loadedCompressSegments.value)
  } catch {
    return []
  }
})

const compressSegmentOptions = computed(() => {
  const existing = loadedCompressSegments.value.map((row) => row.segment_index)
  const next = maxNextSegmentIndex(existing, selectedConversationMaxRounds.value)
  const options: Array<{ index: number; label: string }> = []
  for (const index of [...new Set(existing)].sort((a, b) => a - b)) {
    const range = getSegmentRoundRange(index, selectedConversationMaxRounds.value || 1)
    options.push({
      index,
      label: `段 ${index} · 第 ${range.start}-${range.end} 轮（重跑）`,
    })
  }
  if (next != null) {
    const range = getSegmentRoundRange(next, selectedConversationMaxRounds.value || 1)
    options.push({
      index: next,
      label: `段 ${next} · 第 ${range.start}-${range.end} 轮（新增）`,
    })
  }
  return options
})

const selectedCompressRoundLabel = computed(() => {
  const range = getSegmentRoundRange(
    selectedSegmentIndex.value,
    selectedConversationMaxRounds.value || 1,
  )
  return `第 ${range.start}-${range.end} 轮`
})

const savedPreviewPanel = computed((): SavedPreviewPanel | null => {
  const model = selectedModelNames.value[0] ?? ''

  if (testMode.value === 'single' && promptType.value === 'segment_compress') {
    const row = loadedCompressSegments.value.find(
      (item) => item.segment_index === selectedSegmentIndex.value,
    )
    if (!row) return null
    const previewPayload: Record<string, unknown> = { ...row.expected_result }
    const priorMerge = [...loadedMergeResults.value]
      .filter((item) => item.round_end < row.round_start)
      .sort((a, b) => b.round_end - a.round_end)[0]
    const mergeMemory = priorMerge?.expected_result?.history_memory
    if (mergeMemory) {
      previewPayload._merge_history_memory = mergeMemory
    }
    return {
      title: `已保存 · Compress 段 ${row.segment_index}`,
      meta: [
        `第 ${row.round_start}-${row.round_end} 轮`,
        model,
        row.updated_at ? formatHistoryTime(row.updated_at) : null,
      ]
        .filter(Boolean)
        .join(' · '),
      content: JSON.stringify(previewPayload, null, 2),
      type: 'segment_compress',
    }
  }

  if (testMode.value === 'single' && promptType.value === 'history_merge') {
    if (availableMergeSegments.value.length === 0) return null
    const window = buildMergeSegmentWindow()
    const row = loadedMergeResults.value.find(
      (item) =>
        item.merge_segment_start === window.start
        && item.merge_segment_end === window.end,
    )
    if (!row) return null
    return {
      title: `已保存 · Merge 段 ${window.start}-${window.end}`,
      meta: [
        `第 ${row.round_start}-${row.round_end} 轮`,
        model,
        row.updated_at ? formatHistoryTime(row.updated_at) : null,
      ]
        .filter(Boolean)
        .join(' · '),
      content: JSON.stringify(row.expected_result, null, 2),
      type: 'history_merge',
    }
  }

  if (selectedRpHistoryKey.value && rpHistoryDetail.value) {
    const run =
      rpHistoryDetail.value.model_runs.find((item) => item.model === model)
      ?? rpHistoryDetail.value.model_runs[0]
    if (!run) return null
    if (promptType.value === 'history_merge' && run.merge) {
      return {
        title: '已保存 · Merge',
        meta: [
          model,
          run.merge_run?.updated_at ? formatHistoryTime(run.merge_run.updated_at) : null,
        ]
          .filter(Boolean)
          .join(' · '),
        content: JSON.stringify(run.merge, null, 2),
        type: 'history_merge',
      }
    }
    if (run.compress) {
      const previewPayload: Record<string, unknown> = { ...run.compress }
      if (run.merge && typeof run.merge === 'object') {
        const mergeMemory = (run.merge as Record<string, unknown>).history_memory
        if (mergeMemory) {
          previewPayload._merge_history_memory = mergeMemory
        }
      }
      return {
        title: '已保存 · Compress',
        meta: [
          `第 ${rpHistoryDetail.value.round_start}-${rpHistoryDetail.value.round_end} 轮`,
          model,
          run.compress_run?.updated_at ? formatHistoryTime(run.compress_run.updated_at) : null,
        ]
          .filter(Boolean)
          .join(' · '),
        content: JSON.stringify(previewPayload, null, 2),
        type: 'segment_compress',
      }
    }
  }

  return null
})

const hasRunResult = computed(
  () =>
    running.value
    || Boolean(lastResponse.value)
    || stepResults.value.length > 0
    || modelRunBundles.value.length > 0,
)

const maxMergeSegmentCount = computed(() =>
  Math.min(4, availableMergeSegments.value.length),
)

const mergeSegmentEndOptions = computed(() => availableMergeSegments.value)

const selectedMergeSegmentsPreview = computed(() => {
  if (availableMergeSegments.value.length === 0) return []
  try {
    return pickConsecutiveSegments(
      availableMergeSegments.value,
      mergeSegmentCount.value,
      mergeSegmentEndIndex.value,
    )
  } catch {
    return []
  }
})

const showRoundRangePicker = computed(() => testMode.value === 'pipeline')

const showCompressSegmentPicker = computed(
  () => testMode.value === 'single' && promptType.value === 'segment_compress',
)

const showMergeSegmentPicker = computed(
  () => testMode.value === 'single' && promptType.value === 'history_merge',
)

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
  roundRange.value = { start: 1, end: Math.min(10, row.message_count) }
  selectedSegmentIndex.value = 1
  void refreshSavedRecords()
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
  void recoverRpTestJob(key)
})

async function refreshSavedRecords() {
  const conv = selectedConversation.value
  const model = selectedModelNames.value[0]
  if (!conv || !model) {
    loadedCompressSegments.value = []
    loadedMergeResults.value = []
    return
  }

  const query = {
    user_id: conv.user_id,
    role_id: conv.role_id,
    app_name: conv.app_name,
    prompt_version: version.value,
    model,
    run_group_id: rpHistoryDetail.value?.run_group_id,
  }

  try {
    loadedCompressSegments.value = await listRpCompressResults(query)
  } catch {
    loadedCompressSegments.value = []
  }

  try {
    loadedMergeResults.value = await listRpMergeResults(query)
  } catch {
    loadedMergeResults.value = []
  }

  const indexes = loadedCompressSegments.value.map((row) => row.segment_index)
  const next = maxNextSegmentIndex(indexes, selectedConversationMaxRounds.value)
  const allowed = new Set([...indexes, ...(next != null ? [next] : [])])
  if (!allowed.has(selectedSegmentIndex.value) && compressSegmentOptions.value.length > 0) {
    selectedSegmentIndex.value = compressSegmentOptions.value[compressSegmentOptions.value.length - 1].index
  }
}

function clampMergeSegmentSelection() {
  const available = availableMergeSegments.value.length
  if (available === 0) {
    mergeSegmentCount.value = 1
    mergeSegmentEndIndex.value = 1
    return
  }
  mergeSegmentCount.value = Math.min(
    Math.max(1, mergeSegmentCount.value),
    Math.min(4, available),
  )
  mergeSegmentEndIndex.value = Math.min(
    Math.max(mergeSegmentCount.value, mergeSegmentEndIndex.value),
    available,
  )
}

function buildMergeSegmentWindow(): { start: number; end: number } {
  return {
    start: mergeSegmentEndIndex.value - mergeSegmentCount.value + 1,
    end: mergeSegmentEndIndex.value,
  }
}

async function runTest() {
  if (selectedRpHistoryKey.value && !rpHistoryDetail.value) {
    await syncRpHistorySelection(selectedRpHistoryKey.value)
  }

  if (!selectedConversation.value) {
    ElMessage.error('请先选择测试用例')
    return
  }

  const models = selectedModelNames.value
  if (models.length === 0) {
    ElMessage.error('请至少选择一个模型')
    return
  }

  if (testMode.value === 'pipeline') {
    const plan = pipelinePlan.value
    if (!plan || plan.segments.length === 0) {
      ElMessage.error('当前轮次范围内没有可执行的 Segment')
      return
    }
  }

  if (testMode.value === 'single' && promptType.value === 'history_merge') {
    await refreshSavedRecords()
    if (availableMergeSegments.value.length === 0) {
      ElMessage.error(
        selectedRpHistoryKey.value
          ? '所选历史无 Compress，无法 Merge'
          : '尚无 Compress 结果，请先运行 Segment 压缩或链路测试',
      )
      return
    }
    clampMergeSegmentSelection()
    if (mergeSegmentCount.value > availableMergeSegments.value.length) {
      ElMessage.error('合并段数超过可用压缩段数量')
      return
    }
    if (selectedMergeSegmentsPreview.value.length === 0) {
      ElMessage.error('当前截至段与合并段数组合无效')
      return
    }
  }

  const modelConfigs: RpTestJobCreateBody['model_configs'] = {}
  for (const model of models) {
    const cfg = resolveRequestWithModelFallback(model)
    if (!cfg) {
      ElMessage.error(`模型 ${model} 配置无效`)
      return
    }
    modelConfigs[model] = {
      base_url: cfg.base_url,
      api_key: cfg.api_key,
      model: cfg.model,
      temperature: cfg.temperature,
      top_k: cfg.top_k ?? null,
      extra_body: cfg.extra_body ?? null,
    }
  }

  const conv = selectedConversation.value
  const body: RpTestJobCreateBody = {
    test_mode: testMode.value,
    prompt_type: promptType.value,
    conversation: {
      conversation_key: conv.conversation_key,
      user_id: conv.user_id,
      role_id: conv.role_id,
      app_name: conv.app_name,
      role_name: conv.role_name,
    },
    models,
    model_configs: modelConfigs,
    version: version.value,
    lang: lang.value,
    rp_history_run_id: rpHistoryDetail.value?.run_group_id,
  }

  if (testMode.value === 'pipeline') {
    body.round_range = { ...roundRange.value }
  } else if (promptType.value === 'segment_compress') {
    body.segment_index = selectedSegmentIndex.value
  } else {
    body.merge_segment_count = mergeSegmentCount.value
    body.merge_segment_end_index = mergeSegmentEndIndex.value
  }

  try {
    reasoningExpanded.value = []
    pipelineForcedTailWarning.value = Boolean(pipelinePlan.value?.hasForcedTailMerge)
    await startRpTestJob({
      body,
      hasForcedTailMerge: pipelinePlan.value?.hasForcedTailMerge,
    })
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '启动测试失败')
  }
}

async function loadRpHistoryOptions() {
  try {
    rpHistoryOptions.value = await listRpHistory()
  } catch {
    rpHistoryOptions.value = []
  }
}

watch(promptType, () => {
  if (jobSnapshot.value?.phase !== 'running') {
    stepResults.value = []
  }
  if (!selectedRpHistoryKey.value || !rpHistoryDetail.value) return
  applyRunMeta(pickRunMetaForPromptType(rpHistoryDetail.value, promptType.value))
  void refreshSavedRecords()
})

watch(selectedRpHistoryKey, (key) => {
  void syncRpHistorySelection(key)
})

watch(
  [
    testMode,
    promptType,
    version,
    selectedConversationKey,
    selectedRpHistoryKey,
    () => selectedModelNames.value.join(','),
    () => rpHistoryDetail.value?.run_group_id,
    () => rpHistoryDetail.value?.model_runs?.length ?? 0,
  ],
  () => {
    void refreshSavedRecords()
  },
)

watch(availableMergeSegments, () => {
  clampMergeSegmentSelection()
})

watch(mergeSegmentCount, () => {
  if (mergeSegmentEndIndex.value < mergeSegmentCount.value) {
    mergeSegmentEndIndex.value = mergeSegmentCount.value
  }
})

const detachRpTestJobRunner = attachRpTestJobRunner({
  onComplete: async (job) => {
    await loadRpHistoryOptions()
    if (selectedRpHistoryKey.value) {
      await syncRpHistorySelection(selectedRpHistoryKey.value)
    }
    const saved = job.progress.saved_count ?? 0
    if (job.models.length === 1) {
      ElMessage.success(saved > 0 ? '测试完成，已保存历史 RP 效果' : '测试完成')
    } else {
      ElMessage.info(`并行测试完成：已保存 ${saved} 个模型`)
    }
  },
  onError: (message) => {
    ElMessage.error(message)
  },
})

subscribeRpTestJob(applyJobSnapshot)

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
  await refreshSavedRecords()
  if (selectedConversationKey.value) {
    await recoverRpTestJob(selectedConversationKey.value)
  }
})

onUnmounted(() => {
  detachRpTestJobRunner()
})

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
            <el-form-item label="测试模式">
              <el-radio-group v-model="testMode">
                <el-radio-button label="pipeline" value="pipeline">链路测试</el-radio-button>
                <el-radio-button label="single" value="single">单步测试</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="showRoundRangePicker" label="测试轮次">
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
              <div v-if="roundRangeHint" class="hint block-hint">
                {{ roundRangeHint }}
              </div>
            </el-form-item>
            <el-form-item v-if="showCompressSegmentPicker" label="压缩段">
              <el-select
                v-model="selectedSegmentIndex"
                placeholder="选择压缩段"
                style="width: 100%"
                :disabled="compressSegmentOptions.length === 0"
              >
                <el-option
                  v-for="option in compressSegmentOptions"
                  :key="option.index"
                  :label="option.label"
                  :value="option.index"
                />
              </el-select>
              <div class="hint block-hint">
                轮次范围：{{ selectedCompressRoundLabel }}（按段累积，重跑同段将覆盖）
              </div>
            </el-form-item>
            <template v-if="showMergeSegmentPicker">
              <el-form-item label="合并段数">
                <el-input-number
                  v-model="mergeSegmentCount"
                  :min="1"
                  :max="maxMergeSegmentCount || 1"
                  :disabled="availableMergeSegments.length === 0"
                  controls-position="right"
                />
                <span class="hint">可选 1-4 段，上限为可用压缩段数</span>
              </el-form-item>
              <el-form-item label="截至段">
                <el-select
                  v-model="mergeSegmentEndIndex"
                  placeholder="选择截至段"
                  style="width: 100%"
                  :disabled="availableMergeSegments.length === 0"
                >
                  <el-option
                    v-for="segment in mergeSegmentEndOptions"
                    :key="segment.index"
                    :label="mergeSegmentOptionLabel(segment)"
                    :value="segment.index"
                    :disabled="segment.index < mergeSegmentCount"
                  />
                </el-select>
                <div v-if="availableMergeSegments.length === 0" class="hint block-hint">
                  请先运行 Segment 压缩或链路测试，或选择含 Compress 的历史记录
                </div>
              </el-form-item>
              <el-form-item v-if="selectedMergeSegmentsPreview.length > 0" label="合并预览">
                <ul class="pipeline-step-list merge-segment-preview">
                  <li
                    v-for="segment in selectedMergeSegmentsPreview"
                    :key="`${segment.id}-${segment.start_round}-${segment.end_round}`"
                  >
                    段 {{ segment.id }} · 第 {{ segment.start_round }}-{{ segment.end_round }} 轮
                  </li>
                </ul>
              </el-form-item>
            </template>
            <el-form-item
              v-if="testMode === 'pipeline' && pipelinePlan"
              label="执行计划"
              class="pipeline-form-item"
            >
              <div class="pipeline-preview">
                <div class="pipeline-preview-summary">{{ pipelinePreviewSummary }}</div>
                <ul v-if="pipelineCycleLines.length > 0" class="pipeline-step-list">
                  <li v-for="(line, lineIndex) in pipelineCycleLines" :key="`${line}-${lineIndex}`">
                    {{ line }}
                  </li>
                </ul>
              </div>
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
            <el-form-item v-if="testMode === 'single'" label="类型">
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
            <el-form-item>
              <el-button
                type="primary"
                :loading="running"
                :disabled="!hasValidRuntime || running"
                @click="runTest"
              >
                {{ testMode === 'pipeline' ? '运行链路测试' : '运行测试' }}
              </el-button>
              <p v-if="jobProgressHint" class="hint block-hint job-progress-hint">
                {{ jobProgressHint }}
              </p>
            </el-form-item>
            </el-form>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12" class="main-col">
        <el-card shadow="never" class="result-card">
          <template #header>
            <div class="panel-header result-card-header">
              <span class="panel-title">返回结果</span>
              <div v-if="savedPreviewPanel" class="saved-preview-header">
                <span class="saved-preview-title">{{ savedPreviewPanel.title }}</span>
                <span class="saved-preview-meta">{{ savedPreviewPanel.meta }}</span>
              </div>
            </div>
          </template>

          <div class="run-result-body">
          <div v-if="savedPreviewPanel" class="saved-preview-block">
            <ResultPanel
              :content="savedPreviewPanel.content"
              :prompt-type="savedPreviewPanel.type"
            />
            <el-divider v-if="hasRunResult" />
          </div>
          <div
            v-if="hasRunResult"
            class="run-result-extra"
            :class="savedPreviewPanel ? 'run-result-extra--with-preview' : 'run-result-extra--solo'"
          >
          <el-alert
            v-if="pipelineForcedTailWarning"
            class="pipeline-warning"
            type="warning"
            :closable="false"
            show-icon
            title="尾批不足 4 段，已按测试策略强制合并"
          />
          <template v-if="modelRunBundles.length > 0">
            <div
              v-for="(bundle, bundleIndex) in modelRunBundles"
              :key="bundle.model"
              class="model-run-block"
            >
              <h4 class="step-title">模型 · {{ bundle.model }}</h4>
              <p v-if="bundle.error" class="model-run-error">{{ bundle.error }}</p>
              <template v-else-if="bundle.steps.length > 1">
                <div
                  v-for="(step, stepIndex) in bundle.steps"
                  :key="`${bundle.model}-${stepIndex}`"
                  class="step-block"
                >
                  <h5 class="step-subtitle">{{ step.stepLabel || promptTypeLabel(step.promptType) }}</h5>
                  <div class="usage">
                    <el-tag>HTTP {{ step.response.status }}</el-tag>
                    <span v-if="step.response.usage">
                      prompt: {{ step.response.usage.prompt_tokens ?? 'N/A' }} |
                      completion: {{ step.response.usage.completion_tokens ?? 'N/A' }} |
                      total: {{ step.response.usage.total_tokens ?? 'N/A' }}
                    </span>
                  </div>
                  <ResultPanel
                    v-if="step.rawContent"
                    :content="step.rawContent"
                    :prompt-type="step.promptType"
                  />
                  <el-divider v-if="stepIndex < bundle.steps.length - 1" />
                </div>
              </template>
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
              <el-divider v-if="bundleIndex < modelRunBundles.length - 1" />
            </div>
          </template>
          <template v-else-if="stepResults.length > 1">
            <div
              v-for="(step, index) in stepResults"
              :key="`${step.promptType}-${index}`"
              class="step-block"
            >
              <h4 class="step-title">{{ step.stepLabel || promptTypeLabel(step.promptType) }}</h4>
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

            <div v-if="rawContent" class="run-result-panel-host">
              <ResultPanel :content="rawContent" :prompt-type="promptType" />
            </div>
          </template>
          </div>
          <el-empty
            v-if="!hasRunResult && !savedPreviewPanel"
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

.input-card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
  overflow-y: auto;
}

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
  overflow: visible;
}

.input-form {
  flex-shrink: 0;
}

.input-form :deep(.el-form-item__content) {
  overflow: visible;
  line-height: 1.5;
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

.pipeline-form-item :deep(.el-form-item__content) {
  width: 100%;
  min-width: 0;
}

.pipeline-preview {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  overflow: visible;
}

.pipeline-preview-summary {
  font-size: 13px;
  line-height: 1.5;
  color: #606266;
  font-weight: 500;
}

.pipeline-step-list {
  margin: 8px 0 0;
  padding: 0 0 0 18px;
  font-size: 13px;
  line-height: 1.6;
  color: #909399;
  list-style: disc;
  list-style-position: outside;
}

.pipeline-step-list li {
  word-break: break-word;
  white-space: normal;
}

.pipeline-step-list li + li {
  margin-top: 6px;
}

.merge-segment-preview {
  margin-top: 0;
}

.pipeline-warning {
  margin-bottom: 12px;
}

.result-card-header {
  width: 100%;
}

.saved-preview-header {
  min-width: 0;
  max-width: 62%;
  text-align: right;
}

.saved-preview-title {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  line-height: 1.4;
}

.saved-preview-header .saved-preview-meta {
  display: block;
  margin: 0;
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.saved-preview-block {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  margin-bottom: 4px;
}

.saved-preview-block :deep(.result-panel) {
  flex: 1;
  min-height: 0;
}

.step-subtitle {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
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
  overflow: hidden;
}

.run-result-extra--with-preview {
  flex-shrink: 0;
  max-height: 42%;
  overflow: auto;
}

.run-result-extra--solo {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.run-result-panel-host {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.run-result-panel-host :deep(.result-panel) {
  flex: 1;
  min-height: 0;
}

.reasoning-tag {
  margin-left: 8px;
}
</style>
