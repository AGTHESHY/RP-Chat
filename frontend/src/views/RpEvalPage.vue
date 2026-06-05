<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getChatQaConversation,
  getRpEval,
  getRpHistoryDetail,
  listRpEvaluations,
  listRpHistory,
  streamChatCompletion,
  deleteRpEval,
  saveRpEval,
  type RpEvalDetail,
  type RpEvalSummary,
  type RpHistoryDetail,
  type RpHistoryModelRun,
  type RpHistorySummary,
} from '../api'
import ApiRuntimePicker from '../components/ApiRuntimePicker.vue'
import RpEvalResultView from '../components/RpEvalResultView.vue'
import StreamResultPanel from '../components/StreamResultPanel.vue'
import ThreeColumnPage from '../components/layout/ThreeColumnPage.vue'
import AppPanel from '../components/layout/AppPanel.vue'
import FilterBar from '../components/layout/FilterBar.vue'
import RuntimeParamsFields from '../components/RuntimeParamsFields.vue'
import { formatConfidence, formatHistoryTime } from '../utils/format'
import {
  formatEvalHistoryLabel,
  formatEvalPromptVersions,
  formatEvaluatedModels,
  formatRpHistoryModelCount,
} from '../utils/rpEvalFormat'
import { usePageRuntime } from '../composables/usePageRuntime'
import {
  buildRpEvalUserContent,
  pickEvaluableModelRuns,
} from '../utils/rpEvalPayload'
import {
  formatEvaluatedModelsLabel,
  parseRpEvalJson,
  type RpEvalParsed,
} from '../utils/parseRpEvalJson'
import { DEEPSEEK_JSON_OUTPUT_EXTRA } from '../utils/apiProfileStorage'
import {
  computeAdaptiveChatTimeout,
  computeAdaptiveMaxCompletionTokens,
} from '../utils/chatCompletionTimeout'
import {
  loadRpEvalSystemPrompt,
  resetRpEvalSystemPrompt,
  saveRpEvalSystemPrompt,
} from '../utils/rpEvalPromptStorage'
import { filterEvaluationsForTask } from '../utils/rpTaskMatch'

const evalRuntime = usePageRuntime('eval')
const { runtime, resolvedRequest, syncWithRegistry } = evalRuntime

const rpHistoryList = ref<RpHistorySummary[]>([])
const rpHistoryLoading = ref(false)
const filterRoleName = ref('')
const selectedRpHistoryKey = ref('')
const rpHistoryDetail = ref<RpHistoryDetail | null>(null)

const historyTab = ref<'rp-test' | 'eval'>('rp-test')
/** 勾选参与横向对比测评的被测模型 */
const checkedEvalModels = ref<string[]>([])
const detailLoading = ref(false)

const evalSystemPrompt = ref(loadRpEvalSystemPrompt())
const evaluating = ref(false)
const evalHistory = ref<RpEvalSummary[]>([])
const evalHistoryLoading = ref(false)
const selectedEvalId = ref<number | null>(null)
const selectedEvalDetail = ref<RpEvalDetail | null>(null)
const viewingEvalRecord = ref(false)
const currentRaw = ref('')
const currentReasoning = ref('')
const streaming = ref(false)
const streamPanelActive = ref(false)
let streamAbort: AbortController | null = null
const currentParsed = ref<RpEvalParsed | null>(null)

const selectedRpHistorySummary = computed(
  () =>
    rpHistoryList.value.find((item) => item.history_key === selectedRpHistoryKey.value) ??
    null,
)

const modelRuns = computed(() => rpHistoryDetail.value?.model_runs ?? [])

const modelTablePaneRef = ref<HTMLElement | null>(null)
const modelTableMaxHeight = ref<number | undefined>(undefined)
const modelTableCompact = ref(false)
let modelTableResizeObserver: ResizeObserver | null = null

function syncModelTableLayout() {
  const pane = modelTablePaneRef.value
  if (!pane || historyTab.value !== 'rp-test') {
    modelTableMaxHeight.value = undefined
    return
  }

  modelTableCompact.value = pane.clientWidth < 360

  // 该容器已被 flex 链约束为「可用高度」。直接作为 el-table 的 max-height：
  // 行少时表格按内容自动收缩（不留白），行多时在表格内部出现滚动条。
  const available = Math.floor(pane.clientHeight)
  modelTableMaxHeight.value = available > 60 ? available : undefined
}

function bindModelTableResizeObserver() {
  modelTableResizeObserver?.disconnect()
  const pane = modelTablePaneRef.value
  if (!pane) return
  modelTableResizeObserver = new ResizeObserver(() => {
    void syncModelTableLayout()
  })
  modelTableResizeObserver.observe(pane)
  const tabs = pane.closest('.history-tabs')
  if (tabs instanceof HTMLElement) {
    modelTableResizeObserver.observe(tabs)
  }
}

watch(
  [modelRuns, selectedRpHistoryKey, historyTab, detailLoading],
  async () => {
    await nextTick()
    bindModelTableResizeObserver()
    syncModelTableLayout()
  },
)

const selectedModelRuns = computed(() => {
  const base = rpHistoryDetail.value
  if (!base || checkedEvalModels.value.length === 0) return []
  return pickEvaluableModelRuns(base, checkedEvalModels.value)
})

const canRunEval = computed(() => {
  if (!selectedRpHistoryKey.value || !rpHistoryDetail.value) return false
  return selectedModelRuns.value.length > 0 && Boolean(resolvedRequest.value)
})

const runtimeParamsHidden = computed(
  () => evaluating.value || streaming.value || streamPanelActive.value,
)

function showRuntimeParamsAgain() {
  streamPanelActive.value = false
}

function isModelRunEvaluable(run: RpHistoryModelRun): boolean {
  return Boolean(run.compress || run.merge)
}

function isModelRunChecked(run: RpHistoryModelRun): boolean {
  return checkedEvalModels.value.includes(run.model)
}

function modelRunRowClassName({ row }: { row: RpHistoryModelRun }) {
  return isModelRunChecked(row) ? 'rp-test-row--selected' : ''
}

function toggleModelCheck(run: RpHistoryModelRun, checked: boolean) {
  if (!isModelRunEvaluable(run)) return
  const set = new Set(checkedEvalModels.value)
  if (checked) {
    set.add(run.model)
  } else {
    set.delete(run.model)
  }
  checkedEvalModels.value = [...set]
}

function syncDefaultCheckedModels() {
  const runs = rpHistoryDetail.value?.model_runs ?? []
  const evaluable = runs.filter(isModelRunEvaluable)
  if (evaluable.length === 0) {
    checkedEvalModels.value = []
    return
  }
  const kept = checkedEvalModels.value.filter((m) =>
    evaluable.some((r) => r.model === m),
  )
  checkedEvalModels.value = kept.length > 0 ? kept : [evaluable[0].model]
}

const selectedEvalSummary = computed(
  () => evalHistory.value.find((item) => item.id === selectedEvalId.value) ?? null,
)

const evalRecordTemperature = computed(() => {
  if (!viewingEvalRecord.value || !selectedEvalDetail.value) return null
  const value = selectedEvalDetail.value.temperature
  return typeof value === 'number' && Number.isFinite(value) ? value : null
})

const evalRecordTopK = computed(() => {
  if (!viewingEvalRecord.value || !selectedEvalDetail.value) return null
  const value = selectedEvalDetail.value.top_k
  return typeof value === 'number' && Number.isFinite(value) ? value : null
})

const selectedEvalModeLabel = computed(() => {
  const detail = selectedEvalDetail.value
  const summary = selectedEvalSummary.value
  const mode = detail?.eval_mode ?? summary?.eval_mode
  if (mode === 'multi_compare') return '多模型对比'
  if (mode === 'single') return '单模型'
  const models = detail?.evaluated_models ?? summary?.evaluated_models ?? []
  return models.length > 1 ? '多模型对比' : '单模型'
})

const selectedEvaluatedModelsLabel = computed(() => {
  const models =
    selectedEvalDetail.value?.evaluated_models ??
    selectedEvalSummary.value?.evaluated_models ??
    []
  return formatEvaluatedModelsLabel(models)
})

const resultPromptVersions = computed(() => {
  const summary = selectedEvalSummary.value
  if (summary && selectedEvalId.value === summary.id) {
    return formatEvalPromptVersions(summary)
  }
  const runs = selectedModelRuns.value
  if (runs.length > 0) {
    const parts: string[] = []
    const compressVersion = runs.find((run) => run.compress)?.compress_run?.prompt_version
    const mergeVersion = runs.find((run) => run.merge)?.merge_run?.prompt_version
    if (compressVersion) parts.push(`C:${compressVersion}`)
    if (mergeVersion) parts.push(`M:${mergeVersion}`)
    return parts.join(' ') || '—'
  }
  return '—'
})

watch(evalSystemPrompt, (text) => {
  saveRpEvalSystemPrompt(text)
})

watch(historyTab, (tab) => {
  if (tab === 'rp-test') {
    viewingEvalRecord.value = false
  }
})

watch(selectedRpHistoryKey, () => {
  selectedEvalId.value = null
  selectedEvalDetail.value = null
  viewingEvalRecord.value = false
  currentRaw.value = ''
  currentParsed.value = null
  void (async () => {
    await syncRpHistorySelection(selectedRpHistoryKey.value)
    await loadEvalHistory()
  })()
})

async function loadRpHistoryList() {
  rpHistoryLoading.value = true
  try {
    rpHistoryList.value = await listRpHistory({
      role_name: filterRoleName.value || undefined,
    })
    if (rpHistoryList.value.length === 0) {
      selectedRpHistoryKey.value = ''
      rpHistoryDetail.value = null
      evalHistory.value = []
      return
    }
    if (
      !selectedRpHistoryKey.value ||
      !rpHistoryList.value.some((item) => item.history_key === selectedRpHistoryKey.value)
    ) {
      selectRpHistory(rpHistoryList.value[0])
    }
  } catch (error) {
    rpHistoryList.value = []
    ElMessage.error(error instanceof Error ? error.message : '加载 RP 历史失败')
  } finally {
    rpHistoryLoading.value = false
  }
}

function selectRpHistory(row: RpHistorySummary) {
  selectedRpHistoryKey.value = row.history_key
}

function onRpHistoryRowClick(row: { conversation_key?: string }) {
  selectRpHistory(row as RpHistorySummary)
}

async function syncRpHistorySelection(key: string) {
  if (!key) {
    rpHistoryDetail.value = null
    checkedEvalModels.value = []
    return
  }
  const summary = selectedRpHistorySummary.value
  if (!summary) return

  detailLoading.value = true
  try {
    rpHistoryDetail.value = await getRpHistoryDetail({
      user_id: summary.user_id,
      role_id: summary.role_id,
      app_name: summary.app_name,
      run_group_id: summary.run_group_id,
    })
    syncDefaultCheckedModels()
  } catch (error) {
    rpHistoryDetail.value = null
    checkedEvalModels.value = []
    ElMessage.error(error instanceof Error ? error.message : '加载 RP 历史详情失败')
  } finally {
    detailLoading.value = false
  }
}

function onModelRunRowClick(row: RpHistoryModelRun) {
  if (!isModelRunEvaluable(row)) return
  toggleModelCheck(row, !isModelRunChecked(row))
  historyTab.value = 'rp-test'
}

async function loadEvalHistory() {
  const detail = rpHistoryDetail.value
  if (!detail) {
    evalHistory.value = []
    return
  }
  evalHistoryLoading.value = true
  try {
    const all = await listRpEvaluations({
      user_id: detail.user_id,
      role_id: detail.role_id,
      app_name: detail.app_name,
    })
    evalHistory.value = filterEvaluationsForTask(all, detail)
  } catch (error) {
    evalHistory.value = []
    ElMessage.error(error instanceof Error ? error.message : '加载测评历史失败')
  } finally {
    evalHistoryLoading.value = false
  }
}

function handleResetPrompt() {
  evalSystemPrompt.value = resetRpEvalSystemPrompt()
  ElMessage.success('已恢复默认测评 SP')
}

async function handleRunEval() {
  if (!canRunEval.value) {
    if (!selectedRpHistoryKey.value) {
      ElMessage.warning('请先在左侧选择对话')
    } else if (checkedEvalModels.value.length === 0) {
      ElMessage.warning('请在「RP测试历史」中勾选至少一个模型')
    } else if (selectedModelRuns.value.length === 0) {
      ElMessage.warning('所选模型缺少 Compress/Merge 产出')
    } else {
      ElMessage.warning('请先在 API 配置页填写有效 API')
    }
    return
  }

  const detail = rpHistoryDetail.value!
  const modelRuns = selectedModelRuns.value
  const requestConfig = resolvedRequest.value!
  evaluating.value = true
  streaming.value = true
  streamPanelActive.value = true
  viewingEvalRecord.value = false
  currentRaw.value = ''
  currentReasoning.value = ''
  currentParsed.value = null
  selectedEvalId.value = null
  selectedEvalDetail.value = null

  const timeoutSeconds = computeAdaptiveChatTimeout(modelRuns.length)
  streamAbort = new AbortController()

  try {
    const conv = await getChatQaConversation({
      user_id: detail.user_id,
      role_id: detail.role_id,
      app_name: detail.app_name,
    })
    const userContent = buildRpEvalUserContent({
      messages: conv.messages,
      detail,
      modelRuns,
    })

    const evalExtraBody = {
      ...(requestConfig.extra_body ?? {}),
      ...DEEPSEEK_JSON_OUTPUT_EXTRA,
    }
    const resp = await streamChatCompletion(
      {
        base_url: requestConfig.base_url,
        api_key: requestConfig.api_key,
        model: requestConfig.model,
        temperature: requestConfig.temperature,
        top_k: requestConfig.top_k ?? null,
        extra_body: evalExtraBody,
        system_prompt: evalSystemPrompt.value,
        user_content: userContent,
        timeout_seconds: timeoutSeconds,
        max_completion_tokens: computeAdaptiveMaxCompletionTokens(modelRuns.length),
      },
      {
        onContent: (_piece, full) => {
          currentRaw.value = full
        },
        onReasoning: (_piece, full) => {
          currentReasoning.value = full
        },
      },
      streamAbort.signal,
    )

    const raw = resp.raw_content || resp.error || ''
    currentRaw.value = raw

    if (resp.status !== 200) {
      const errDetail = (resp.error || '').trim().slice(0, 240)
      ElMessage.error(
        errDetail
          ? `测评请求失败: HTTP ${resp.status} — ${errDetail}`
          : `测评请求失败: HTTP ${resp.status}`,
      )
      streaming.value = false
      return
    }

    const parsed = parseRpEvalJson(raw)
    if (!parsed.ok || !parsed.data) {
      ElMessage.warning(parsed.error || '测评 JSON 解析失败，未入库')
      streaming.value = false
      return
    }
    currentParsed.value = parsed.data

    const evaluatedModels = modelRuns.map((r) => r.model)
    const evalMode = evaluatedModels.length > 1 ? 'multi_compare' : 'single'
    const firstRun = modelRuns[0]
    const saved = await saveRpEval({
      user_id: detail.user_id,
      role_id: detail.role_id,
      app_name: detail.app_name,
      role_name: detail.role_name,
      round_start: detail.round_start,
      round_end: detail.round_end,
      has_compress: modelRuns.some((r) => r.compress),
      has_merge: modelRuns.some((r) => r.merge),
      compress_prompt_version: firstRun?.compress_run?.prompt_version ?? detail.prompt_version,
      merge_prompt_version: firstRun?.merge_run?.prompt_version ?? '',
      eval_system_prompt: evalSystemPrompt.value,
      eval_result: JSON.parse(JSON.stringify(parsed.data)) as Record<string, unknown>,
      raw_model_output: raw,
      model: requestConfig.model,
      top_k: requestConfig.top_k ?? null,
      temperature: requestConfig.temperature,
      eval_mode: evalMode,
      evaluated_models: evaluatedModels,
      run_group_id: detail.run_group_id,
    })

    selectedEvalId.value = saved.id
    await loadEvalHistory()
    streaming.value = false
    ElMessage.success('测评完成并已保存')
  } catch (error) {
    streaming.value = false
    if (error instanceof DOMException && error.name === 'AbortError') {
      ElMessage.error(`测评超时（连续 ${timeoutSeconds}s 无数据），请重试或减少对比模型数`)
    } else {
      ElMessage.error(error instanceof Error ? error.message : '测评失败')
    }
  } finally {
    streamAbort = null
    evaluating.value = false
  }
}

async function selectEvalRow(row: RpEvalSummary) {
  historyTab.value = 'eval'
  selectedEvalId.value = row.id
  viewingEvalRecord.value = true
  streaming.value = false
  streamPanelActive.value = false
  currentReasoning.value = ''
  try {
    const detail = await getRpEval(row.id)
    selectedEvalDetail.value = detail
    currentRaw.value = detail.raw_model_output
    const parsed = parseRpEvalJson(JSON.stringify(detail.eval_result))
    currentParsed.value = parsed.ok ? parsed.data ?? null : null
  } catch (error) {
    selectedEvalDetail.value = null
    currentParsed.value = null
    ElMessage.error(error instanceof Error ? error.message : '加载测评详情失败')
  }
}

function onEvalRowClick(row: RpEvalSummary) {
  historyTab.value = 'eval'
  void selectEvalRow(row)
}

async function removeEvalRecord() {
  if (!selectedEvalId.value) return
  try {
    await ElMessageBox.confirm('确定删除该条测评记录？', '删除测评', { type: 'warning' })
    await deleteRpEval(selectedEvalId.value)
    selectedEvalId.value = null
    selectedEvalDetail.value = null
    viewingEvalRecord.value = false
    currentRaw.value = ''
    currentParsed.value = null
    await loadEvalHistory()
    ElMessage.success('已删除测评记录')
  } catch {
    /* cancelled */
  }
}

onMounted(async () => {
  syncWithRegistry()
  await loadRpHistoryList()
  await nextTick()
  bindModelTableResizeObserver()
  syncModelTableLayout()
})

onUnmounted(() => {
  modelTableResizeObserver?.disconnect()
  modelTableResizeObserver = null
  streamAbort?.abort()
  streamAbort = null
})
</script>

<template>
  <ThreeColumnPage>
    <template #left>
      <AppPanel title="RP 历史">
        <template #actions>
          <el-button size="small" @click="loadRpHistoryList">刷新</el-button>
        </template>
        <div class="rp-eval-left-body">
        <FilterBar @query="loadRpHistoryList">
          <el-input
            v-model="filterRoleName"
            placeholder="模糊搜索角色名"
            clearable
            size="small"
            @keyup.enter="loadRpHistoryList"
            @clear="loadRpHistoryList"
          />
        </FilterBar>
          <el-table
            v-loading="rpHistoryLoading"
            :data="rpHistoryList"
            highlight-current-row
            class="record-table"
            size="small"
            :current-row-key="selectedRpHistoryKey"
            row-key="history_key"
            @row-click="onRpHistoryRowClick"
          >
            <el-table-column prop="role_name" label="角色" min-width="72" show-overflow-tooltip />
            <el-table-column label="轮次" width="72">
              <template #default="{ row }">
                {{ row.round_start }}-{{ row.round_end }}
              </template>
            </el-table-column>
            <el-table-column prop="prompt_version" label="SP" width="48" show-overflow-tooltip />
            <el-table-column label="模型数" width="52" align="center">
              <template #default="{ row }">
                {{
                  formatRpHistoryModelCount(
                    row as RpHistorySummary,
                    selectedRpHistoryKey,
                    rpHistoryDetail,
                  )
                }}
              </template>
            </el-table-column>
          </el-table>
          <p v-if="!rpHistoryLoading && rpHistoryList.length === 0" class="list-hint">
            暂无历史，请先在 RP 测试页运行测试
          </p>

          <el-tabs v-model="historyTab" class="history-tabs" stretch>
            <el-tab-pane label="RP测试历史" name="rp-test">
              <div ref="modelTablePaneRef" class="history-tab-pane-inner">
                <p v-if="!selectedRpHistoryKey" class="list-hint tab-pane-hint">
                  请先在上方选择对话
                </p>
                <div v-else class="rp-model-table-wrap">
                  <el-table
                    v-loading="detailLoading"
                    :data="modelRuns"
                    :max-height="modelTableMaxHeight"
                    class="eval-table rp-test-table"
                    size="small"
                    empty-text="暂无测试记录，请先在 RP 测试页运行"
                    :row-class-name="modelRunRowClassName"
                    @row-click="onModelRunRowClick"
                  >
                    <el-table-column
                      prop="model"
                      label="模型"
                      :min-width="modelTableCompact ? 64 : 80"
                      show-overflow-tooltip
                    />
                    <el-table-column
                      label="压缩"
                      :width="modelTableCompact ? 40 : 48"
                      align="center"
                      class-name="col-nowrap"
                    >
                      <template #default="{ row }">
                        {{ row.compress ? '有' : '—' }}
                      </template>
                    </el-table-column>
                    <el-table-column
                      label="合并"
                      :width="modelTableCompact ? 40 : 48"
                      align="center"
                      class-name="col-nowrap"
                    >
                      <template #default="{ row }">
                        {{ row.merge ? '有' : '—' }}
                      </template>
                    </el-table-column>
                    <el-table-column
                      label="时间"
                      :min-width="modelTableCompact ? 56 : 68"
                      class-name="col-nowrap"
                    >
                      <template #default="{ row }">
                        {{ formatHistoryTime(row.latest_updated_at) }}
                      </template>
                    </el-table-column>
                    <el-table-column
                      label="对比"
                      :width="modelTableCompact ? 40 : 44"
                      align="center"
                      :fixed="modelTableCompact ? false : 'right'"
                    >
                      <template #default="{ row }">
                        <el-checkbox
                          :model-value="isModelRunChecked(row)"
                          :disabled="!isModelRunEvaluable(row)"
                          @click.stop
                          @change="(v: boolean) => toggleModelCheck(row, v)"
                        />
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </div>
            </el-tab-pane>
            <el-tab-pane label="测评历史" name="eval">
              <div class="history-tab-pane-inner">
                <div class="sub-panel-title sub-panel-title-row tab-pane-toolbar">
                  <span />
                  <el-button
                    size="small"
                    type="danger"
                    plain
                    :disabled="!selectedEvalId || historyTab !== 'eval'"
                    @click="removeEvalRecord"
                  >
                    删除
                  </el-button>
                </div>
                <div class="tab-pane-table-wrap">
                  <el-table
                    v-loading="evalHistoryLoading"
                    :data="evalHistory"
                    highlight-current-row
                    class="eval-table"
                    size="small"
                    empty-text="暂无测评"
                    @row-click="onEvalRowClick"
                  >
                <el-table-column label="时间" min-width="88">
                  <template #default="{ row }">
                    {{ formatHistoryTime(row.created_at) }}
                  </template>
                </el-table-column>
                <el-table-column label="SP版本" min-width="88" show-overflow-tooltip>
                  <template #default="{ row }">
                    {{ formatEvalPromptVersions(row as RpEvalSummary) }}
                  </template>
                </el-table-column>
                <el-table-column label="被测" width="48" show-overflow-tooltip>
                  <template #default="{ row }">
                    {{ formatEvaluatedModels(row as RpEvalSummary) }}
                  </template>
                </el-table-column>
                <el-table-column label="分" width="40" prop="overall_score" />
                <el-table-column label="置信" width="52">
                  <template #default="{ row }">
                    {{ formatConfidence(row.overall_confidence) }}
                  </template>
                </el-table-column>
              </el-table>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </AppPanel>
    </template>

    <template #center>
      <AppPanel title="编辑测评 SP">
        <template #actions>
          <el-button size="small" @click="handleResetPrompt">恢复默认</el-button>
        </template>
          <el-empty
            v-if="!selectedRpHistoryKey && !selectedEvalSummary"
            description="请选择对话，或在「测评历史」选择记录"
          />
          <el-form v-else label-width="88px" class="edit-form">
            <el-form-item label="角色">
              <el-input
                :model-value="
                  selectedEvalDetail?.role_name ??
                  selectedEvalSummary?.role_name ??
                  rpHistoryDetail?.role_name ??
                  '—'
                "
                disabled
              />
            </el-form-item>
            <template v-if="viewingEvalRecord && selectedEvalSummary">
              <el-form-item label="测评摘要">
                <el-input
                  :model-value="formatEvalHistoryLabel(selectedEvalSummary)"
                  disabled
                />
              </el-form-item>
              <el-form-item label="被测 SP">
                <el-input
                  :model-value="formatEvalPromptVersions(selectedEvalSummary)"
                  disabled
                />
              </el-form-item>
              <el-form-item label="测评模式">
                <el-input :model-value="selectedEvalModeLabel" disabled />
              </el-form-item>
              <el-form-item label="被测模型">
                <el-input :model-value="selectedEvaluatedModelsLabel" disabled />
              </el-form-item>
              <el-form-item label="测评分">
                <el-input
                  :model-value="`${selectedEvalSummary.overall_score} / 置信 ${formatConfidence(selectedEvalSummary.overall_confidence)}`"
                  disabled
                />
              </el-form-item>
            </template>
            <template v-else>
              <el-form-item label="轮次">
                <el-input
                  :model-value="
                    rpHistoryDetail
                      ? `${rpHistoryDetail.round_start} - ${rpHistoryDetail.round_end}`
                      : '—'
                  "
                  disabled
                />
              </el-form-item>
              <el-form-item label="SP 版本">
                <el-input :model-value="rpHistoryDetail?.prompt_version ?? '—'" disabled />
              </el-form-item>
              <el-form-item label="对比模型">
                <el-input
                  :model-value="formatEvaluatedModelsLabel(checkedEvalModels)"
                  disabled
                />
              </el-form-item>
              <el-form-item label="被测产出">
                <el-input
                  :model-value="
                    selectedModelRuns.length
                      ? selectedModelRuns
                          .map(
                            (run) =>
                              `${run.model}: ${
                                [
                                  run.compress ? 'C' : '',
                                  run.merge ? 'M' : '',
                                ]
                                  .filter(Boolean)
                                  .join('+') || '—'
                              }`,
                          )
                          .join('；')
                      : '—'
                  "
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  disabled
                />
              </el-form-item>
            </template>
            <el-form-item label="测评 SP" class="content-item">
              <el-input
                v-model="evalSystemPrompt"
                type="textarea"
                class="content-editor"
                placeholder="测评用 System Prompt"
              />
            </el-form-item>
            <div class="char-count">{{ evalSystemPrompt.length }} 字符</div>
          </el-form>
      </AppPanel>
    </template>

    <template #right>
      <AppPanel title="RP 测评" title-class="panel-title-with-picker">
        <template #title>
          <span>RP 测评</span>
          <ApiRuntimePicker scope="eval" />
        </template>
        <div
          class="test-panel-body"
          :class="{ 'test-panel-body--preview': viewingEvalRecord || runtimeParamsHidden }"
        >
          <Transition name="params-collapse">
            <el-form
              v-if="!viewingEvalRecord && !runtimeParamsHidden"
              label-width="88px"
              class="test-form"
            >
              <RuntimeParamsFields
                :temperature="runtime.temperature"
                :top-k="runtime.top_k"
                @update:temperature="runtime.temperature = $event"
                @update:top-k="runtime.top_k = $event"
              >
                <template #top-k-suffix>
                  <el-button
                    type="primary"
                    :loading="evaluating"
                    :disabled="!canRunEval"
                    @click="handleRunEval"
                  >
                    开始测评
                  </el-button>
                </template>
              </RuntimeParamsFields>
            </el-form>
          </Transition>

          <div v-if="streamPanelActive || currentRaw || currentParsed" class="result-block">
            <div class="result-title-row">
              <div class="result-title-main">
                <span class="result-title">
                  {{
                    streaming
                      ? '测评生成中'
                      : viewingEvalRecord && selectedEvalId
                        ? `测评记录 #${selectedEvalId}`
                        : selectedEvalId
                          ? `测评结果 #${selectedEvalId}`
                          : '本次测评结果'
                  }}
                </span>
                <span
                  v-if="resultPromptVersions !== '—'"
                  class="result-prompt-versions"
                >
                  {{ resultPromptVersions }}
                </span>
              </div>
              <div
                v-if="viewingEvalRecord && (evalRecordTemperature !== null || evalRecordTopK !== null)"
                class="result-meta-chips"
              >
                <span
                  v-if="evalRecordTemperature !== null"
                  class="record-meta-chip"
                >
                  <span class="record-meta-label">temperature</span>
                  <span class="record-meta-value">{{ evalRecordTemperature }}</span>
                </span>
                <span v-if="evalRecordTopK !== null" class="record-meta-chip">
                  <span class="record-meta-label">top_k</span>
                  <span class="record-meta-value">{{ evalRecordTopK }}</span>
                </span>
              </div>
              <el-button
                v-else-if="runtimeParamsHidden && !streaming && !evaluating"
                link
                type="primary"
                size="small"
                @click="showRuntimeParamsAgain"
              >
                重新测评
              </el-button>
            </div>
            <StreamResultPanel
              v-if="streamPanelActive"
              class="result-scroll"
              :streaming="streaming"
              :content="currentRaw"
              :reasoning="currentReasoning"
            >
              <RpEvalResultView :raw-content="currentRaw" :parsed="currentParsed" />
            </StreamResultPanel>
            <el-scrollbar v-else class="result-scroll">
              <RpEvalResultView :raw-content="currentRaw" :parsed="currentParsed" />
            </el-scrollbar>
          </div>
          <el-empty
            v-else
            class="result-empty"
            description="在「RP测试历史」确认产出后运行测评，或在「测评历史」查看记录"
            :image-size="56"
          />
        </div>
      </AppPanel>
    </template>
  </ThreeColumnPage>
</template>

<style scoped>
.test-panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.content-editor :deep(.el-textarea__inner) {
  min-height: 180px;
}

.test-panel-body--preview .result-block {
  padding-top: 14px;
}

.params-collapse-leave-active {
  transition:
    opacity 0.35s ease,
    max-height 0.5s cubic-bezier(0.4, 0, 0.2, 1),
    margin 0.5s cubic-bezier(0.4, 0, 0.2, 1),
    padding 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.params-collapse-leave-from {
  opacity: 1;
  max-height: 100px;
}

.params-collapse-leave-to {
  opacity: 0;
  max-height: 0;
  margin-bottom: 0;
  padding-bottom: 0;
}

.params-collapse-enter-active {
  transition:
    opacity 0.4s ease 0.08s,
    max-height 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.params-collapse-enter-from {
  opacity: 0;
  max-height: 0;
}

.params-collapse-enter-to {
  opacity: 1;
  max-height: 100px;
}

.result-block {
  flex: 1;
  min-height: 0;
  padding: 0 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
  min-width: 0;
}

.result-title-main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
}

.result-title {
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}

.result-prompt-versions {
  font-size: 12px;
  font-weight: 500;
  color: #909399;
}

.result-meta-chips {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
  min-width: 0;
  flex-shrink: 0;
}

.record-meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
  background: #f4f4f5;
  color: #606266;
}

.record-meta-label {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 400;
  opacity: 0.72;
}

.record-meta-value {
  font-size: 12px;
  font-weight: 500;
}

.result-scroll {
  flex: 1;
  min-height: 0;
}

.result-empty {
  flex: 1;
  padding: 12px;
}

.tab-pane-hint {
  padding: 6px 12px 8px;
  flex-shrink: 0;
}

.rp-eval-left-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.rp-eval-left-body :deep(.record-table) {
  flex: 0 1 auto;
  max-height: 38%;
  min-height: 120px;
}

.rp-eval-left-body .history-tabs {
  flex: 1;
  min-height: 0;
}

/* 关键：让 Tab 内容区与每个 tab-pane 成为受约束的 flex 列容器，
   否则内层会被内容撑高，clientHeight 失真，导致表格无法滚动。 */
.rp-eval-left-body .history-tabs :deep(.el-tabs__content) {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.rp-eval-left-body .history-tabs :deep(.el-tab-pane) {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.history-tab-pane-inner {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.rp-model-table-wrap {
  flex: 0 1 auto;
  min-height: 0;
  max-height: 100%;
  width: 100%;
  overflow: hidden;
}

.rp-test-table {
  width: 100% !important;
}

.rp-test-table :deep(.el-table__body-wrapper) {
  scrollbar-width: thin;
  scrollbar-color: #b1b3b8 transparent;
}

.rp-test-table :deep(.el-table__body-wrapper::-webkit-scrollbar) {
  width: 8px;
  height: 8px;
}

.rp-test-table :deep(.el-table__body-wrapper::-webkit-scrollbar-thumb) {
  background-color: #b1b3b8;
  border-radius: 4px;
}

.rp-test-table :deep(.el-table__body-wrapper::-webkit-scrollbar-thumb:hover) {
  background-color: #909399;
}

.rp-test-table :deep(.el-table__cell) {
  padding: 5px 0;
}

.rp-test-table :deep(.cell) {
  padding: 0 6px;
  font-size: 12px;
}

.tab-pane-toolbar {
  border-top: none;
  min-height: 36px;
}

:deep(.rp-test-row--selected > td) {
  background-color: #ecf5ff !important;
}
</style>
