<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteBrainAnalysis,
  deleteRpEval,
  getBrainAnalysis,
  getRpEval,
  getRpHistoryDetail,
  listBrainAnalyses,
  listRpEvaluations,
  listRpHistory,
  listVersions,
  streamChatCompletion,
  saveBrainAnalysis,
  type BrainAnalysisDetail,
  type BrainAnalysisSummary,
  type RpEvalDetail,
  type RpEvalSummary,
  type RpHistoryDetail,
  type RpHistorySummary,
} from '../api'
import ApiRuntimePicker from '../components/ApiRuntimePicker.vue'
import BrainResultView from '../components/BrainResultView.vue'
import StreamResultPanel from '../components/StreamResultPanel.vue'
import ThreeColumnPage from '../components/layout/ThreeColumnPage.vue'
import AppPanel from '../components/layout/AppPanel.vue'
import FilterBar from '../components/layout/FilterBar.vue'
import RuntimeParamsFields from '../components/RuntimeParamsFields.vue'
import { usePageRuntime } from '../composables/usePageRuntime'
import { DEEPSEEK_JSON_OUTPUT_EXTRA } from '../utils/apiProfileStorage'
import {
  computeAdaptiveChatTimeout,
  computeAdaptiveMaxCompletionTokens,
} from '../utils/chatCompletionTimeout'
import { buildBrainUserPayload, hasMultiModelEvalDimensions } from '../utils/brainPayload'
import {
  buildVersionContext,
  formatVersionKindLabel,
  type BrainVersionContext,
} from '../utils/brainVersionContext'
import {
  loadBrainSystemPrompt,
  resetBrainSystemPrompt,
  saveBrainSystemPrompt,
} from '../utils/brainPromptStorage'
import {
  brainRecommendationLabel,
  parseBrainJson,
  type BrainParsed,
} from '../utils/parseBrainJson'
import {
  formatEvaluatedModelsLabel,
  isMultiCompareEval,
  parseRpEvalJson,
} from '../utils/parseRpEvalJson'
import {
  formatBrainPromptVersions,
  formatEvalHistoryLabel,
  formatEvaluatedModels,
  formatEvalPromptVersions,
} from '../utils/rpEvalFormat'
import { formatConfidence, formatHistoryTime } from '../utils/format'

const brainRuntime = usePageRuntime('brain')
const { runtime, resolvedRequest, syncWithRegistry } = brainRuntime

const rpHistoryList = ref<RpHistorySummary[]>([])
const rpHistoryLoading = ref(false)
const filterRoleName = ref('')
const selectedRpHistoryKey = ref('')
const rpHistoryDetail = ref<RpHistoryDetail | null>(null)

const brainSystemPrompt = ref(loadBrainSystemPrompt())
const analyzing = ref(false)
const historyTab = ref<'eval' | 'brain'>('eval')
const evalHistory = ref<RpEvalSummary[]>([])
const evalHistoryLoading = ref(false)
const selectedEvalId = ref<number | null>(null)
const selectedEvalDetail = ref<RpEvalDetail | null>(null)
const evalVersionContexts = ref<Record<string, BrainVersionContext>>({})

const brainHistory = ref<BrainAnalysisSummary[]>([])
const brainHistoryLoading = ref(false)
const selectedBrainId = ref<number | null>(null)
const selectedBrainDetail = ref<BrainAnalysisDetail | null>(null)

const currentRaw = ref('')
const currentReasoning = ref('')
const streaming = ref(false)
const streamPanelActive = ref(false)
let streamAbort: AbortController | null = null
const currentParsed = ref<BrainParsed | null>(null)
const viewingBrainRecord = ref(false)

const selectedEvalSummary = computed(
  () => evalHistory.value.find((item) => item.id === selectedEvalId.value) ?? null,
)

const selectedBrainSummary = computed(
  () => brainHistory.value.find((item) => item.id === selectedBrainId.value) ?? null,
)

const brainRecordTemperature = computed(() => {
  if (!viewingBrainRecord.value || !selectedBrainDetail.value) return null
  const value = selectedBrainDetail.value.temperature
  return typeof value === 'number' && Number.isFinite(value) ? value : null
})

const brainRecordTopK = computed(() => {
  if (!viewingBrainRecord.value || !selectedBrainDetail.value) return null
  const value = selectedBrainDetail.value.top_k
  return typeof value === 'number' && Number.isFinite(value) ? value : null
})

const linkedEvalLabel = computed(() => {
  const brain = selectedBrainSummary.value
  if (!brain) return '—'
  const evalRow =
    selectedEvalSummary.value?.id === brain.rp_eval_id
      ? selectedEvalSummary.value
      : selectedEvalDetail.value?.id === brain.rp_eval_id
        ? selectedEvalDetail.value
        : (evalHistory.value.find((item) => item.id === brain.rp_eval_id) ?? null)
  if (evalRow) return formatEvalHistoryLabel(evalRow)
  const sp = formatBrainPromptVersions(brain)
  return sp !== '—' ? `${sp}（#${brain.rp_eval_id}）` : `#${brain.rp_eval_id}`
})

const canRunBrain = computed(
  () => Boolean(selectedEvalId.value && selectedEvalDetail.value && resolvedRequest.value),
)

const runtimeParamsHidden = computed(
  () => analyzing.value || streaming.value || streamPanelActive.value,
)

function showRuntimeParamsAgain() {
  streamPanelActive.value = false
}

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

const selectedVersionKindLines = computed(() => {
  const detail = selectedEvalDetail.value
  if (!detail) return []
  const lines: string[] = []
  if (detail.has_compress && detail.compress_prompt_version) {
    const ctx = evalVersionContexts.value[detail.compress_prompt_version]
    lines.push(
      `Compress: ${ctx ? formatVersionKindLabel(ctx) : detail.compress_prompt_version}`,
    )
  }
  if (detail.has_merge && detail.merge_prompt_version) {
    const ctx = evalVersionContexts.value[detail.merge_prompt_version]
    lines.push(`Merge: ${ctx ? formatVersionKindLabel(ctx) : detail.merge_prompt_version}`)
  }
  return lines
})

watch(brainSystemPrompt, (text) => {
  saveBrainSystemPrompt(text)
})

watch(selectedRpHistoryKey, () => {
  selectedEvalId.value = null
  selectedEvalDetail.value = null
  evalVersionContexts.value = {}
  selectedBrainId.value = null
  selectedBrainDetail.value = null
  currentRaw.value = ''
  currentReasoning.value = ''
  streaming.value = false
  streamPanelActive.value = false
  currentParsed.value = null
  viewingBrainRecord.value = false
  void (async () => {
    await syncRpHistorySelection(selectedRpHistoryKey.value)
    await loadEvalHistory()
    await loadBrainHistory()
  })()
})

watch(historyTab, () => {
  if (historyTab.value === 'eval') {
    viewingBrainRecord.value = false
  }
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
    return
  }
  const summary = rpHistoryList.value.find((item) => item.history_key === key)
  if (!summary) return
  try {
    rpHistoryDetail.value = await getRpHistoryDetail({
      user_id: summary.user_id,
      role_id: summary.role_id,
      app_name: summary.app_name,
      run_group_id: summary.run_group_id,
    })
  } catch (error) {
    rpHistoryDetail.value = null
    ElMessage.error(error instanceof Error ? error.message : '加载 RP 历史详情失败')
  }
}

async function loadEvalHistory() {
  if (!rpHistoryDetail.value) {
    evalHistory.value = []
    return
  }
  const detail = rpHistoryDetail.value
  evalHistoryLoading.value = true
  try {
    evalHistory.value = await listRpEvaluations({
      user_id: detail.user_id,
      role_id: detail.role_id,
      app_name: detail.app_name,
    })
  } catch (error) {
    evalHistory.value = []
    ElMessage.error(error instanceof Error ? error.message : '加载测评历史失败')
  } finally {
    evalHistoryLoading.value = false
  }
}

async function loadBrainHistory() {
  if (!rpHistoryDetail.value) {
    brainHistory.value = []
    return
  }
  const detail = rpHistoryDetail.value
  brainHistoryLoading.value = true
  try {
    brainHistory.value = await listBrainAnalyses({
      user_id: detail.user_id,
      role_id: detail.role_id,
      app_name: detail.app_name,
    })
  } catch (error) {
    brainHistory.value = []
    ElMessage.error(error instanceof Error ? error.message : '加载智脑历史失败')
  } finally {
    brainHistoryLoading.value = false
  }
}

function handleResetPrompt() {
  brainSystemPrompt.value = resetBrainSystemPrompt()
  ElMessage.success('已恢复默认智脑 SP')
}

async function loadEvalVersionContexts(detail: RpEvalDetail) {
  const versions = new Set<string>()
  if (detail.compress_prompt_version) versions.add(detail.compress_prompt_version)
  if (detail.merge_prompt_version) versions.add(detail.merge_prompt_version)
  if (versions.size === 0) {
    evalVersionContexts.value = {}
    return
  }
  try {
    const catalog = await listVersions()
    const contexts: Record<string, BrainVersionContext> = {}
    for (const v of versions) {
      contexts[v] = await buildVersionContext(v, catalog)
    }
    evalVersionContexts.value = contexts
  } catch {
    evalVersionContexts.value = {}
  }
}

async function selectEvalRow(row: RpEvalSummary) {
  historyTab.value = 'eval'
  selectedEvalId.value = row.id
  selectedBrainId.value = null
  selectedBrainDetail.value = null
  viewingBrainRecord.value = false
  streaming.value = false
  streamPanelActive.value = false
  currentReasoning.value = ''
  currentRaw.value = ''
  currentParsed.value = null
  evalVersionContexts.value = {}
  try {
    const detail = await getRpEval(row.id)
    selectedEvalDetail.value = detail
    void loadEvalVersionContexts(detail)
  } catch (error) {
    selectedEvalDetail.value = null
    ElMessage.error(error instanceof Error ? error.message : '加载测评详情失败')
  }
}

function onEvalRowClick(row: RpEvalSummary) {
  void selectEvalRow(row)
}

async function selectBrainRow(row: BrainAnalysisSummary) {
  historyTab.value = 'brain'
  selectedBrainId.value = row.id
  viewingBrainRecord.value = true
  streaming.value = false
  streamPanelActive.value = false
  currentReasoning.value = ''
  try {
    const detail = await getBrainAnalysis(row.id)
    selectedBrainDetail.value = detail
    currentRaw.value = detail.raw_model_output
    const parsed = parseBrainJson(JSON.stringify(detail.brain_result))
    currentParsed.value = parsed.ok ? parsed.data ?? null : null
    selectedEvalId.value = detail.rp_eval_id
    try {
      const evalDetail = await getRpEval(detail.rp_eval_id)
      selectedEvalDetail.value = evalDetail
      void loadEvalVersionContexts(evalDetail)
    } catch {
      selectedEvalDetail.value = null
    }
  } catch (error) {
    selectedBrainDetail.value = null
    currentParsed.value = null
    ElMessage.error(error instanceof Error ? error.message : '加载智脑记录失败')
  }
}

function onBrainRowClick(row: BrainAnalysisSummary) {
  void selectBrainRow(row)
}

async function removeEvalRecord() {
  if (!selectedEvalId.value) return
  try {
    await ElMessageBox.confirm('确定删除该条测评记录？', '删除测评', { type: 'warning' })
    await deleteRpEval(selectedEvalId.value)
    selectedEvalId.value = null
    selectedEvalDetail.value = null
    viewingBrainRecord.value = false
    currentRaw.value = ''
    currentParsed.value = null
    await loadEvalHistory()
    ElMessage.success('已删除测评记录')
  } catch {
    /* cancelled */
  }
}

async function removeBrainRecord() {
  if (!selectedBrainId.value) return
  try {
    await ElMessageBox.confirm('确定删除该条智脑分析记录？', '删除智脑', { type: 'warning' })
    await deleteBrainAnalysis(selectedBrainId.value)
    selectedBrainId.value = null
    selectedBrainDetail.value = null
    viewingBrainRecord.value = false
    currentRaw.value = ''
    currentParsed.value = null
    await loadBrainHistory()
    ElMessage.success('已删除智脑记录')
  } catch {
    /* cancelled */
  }
}

async function handleRunBrain() {
  if (!canRunBrain.value || !selectedEvalDetail.value) {
    if (!selectedEvalId.value) {
      ElMessage.warning('请先在左侧选择一条测评历史')
    } else if (!resolvedRequest.value) {
      ElMessage.warning('请先在 API 配置页填写有效 API')
    }
    return
  }

  const evalDetail = selectedEvalDetail.value
  const requestConfig = resolvedRequest.value!
  const evalMode =
    evalDetail.eval_mode ??
    (evalDetail.evaluated_models?.length > 1 ? 'multi_compare' : 'single')
  const parsedEval = parseRpEvalJson(JSON.stringify(evalDetail.eval_result))
  if (
    evalMode === 'multi_compare' &&
    parsedEval.ok &&
    parsedEval.data &&
    isMultiCompareEval(parsedEval.data) &&
    !hasMultiModelEvalDimensions(evalDetail.eval_result)
  ) {
    ElMessage.warning('测评 JSON 不完整，智脑可能无法给出模型对比建议')
  }
  analyzing.value = true
  streaming.value = true
  streamPanelActive.value = true
  viewingBrainRecord.value = false
  currentRaw.value = ''
  currentReasoning.value = ''
  currentParsed.value = null

  const evaluatedModelCount = Math.max(
    1,
    evalDetail.evaluated_models?.length ?? (evalMode === 'multi_compare' ? 2 : 1),
  )
  const timeoutSeconds = computeAdaptiveChatTimeout(evaluatedModelCount)
  streamAbort = new AbortController()

  try {
    const versionCatalog = await listVersions()
    const userContent = await buildBrainUserPayload({ evalDetail, versionCatalog })
    const extra = {
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
        extra_body: extra,
        system_prompt: brainSystemPrompt.value,
        user_content: userContent,
        timeout_seconds: timeoutSeconds,
        max_completion_tokens: computeAdaptiveMaxCompletionTokens(evaluatedModelCount),
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
          ? `智脑请求失败: HTTP ${resp.status} — ${errDetail}`
          : `智脑请求失败: HTTP ${resp.status}`,
      )
      streaming.value = false
      streamPanelActive.value = false
      return
    }

    const parsed = parseBrainJson(raw)
    if (!parsed.ok || !parsed.data) {
      ElMessage.warning(parsed.error || '智脑 JSON 解析失败')
      streaming.value = false
      streamPanelActive.value = false
      return
    }
    currentParsed.value = parsed.data
    viewingBrainRecord.value = false

    const saved = await saveBrainAnalysis({
      rp_eval_id: evalDetail.id,
      user_id: evalDetail.user_id,
      role_id: evalDetail.role_id,
      app_name: evalDetail.app_name,
      role_name: evalDetail.role_name,
      round_start: evalDetail.round_start,
      round_end: evalDetail.round_end,
      compress_prompt_version: evalDetail.compress_prompt_version,
      merge_prompt_version: evalDetail.merge_prompt_version,
      brain_system_prompt: brainSystemPrompt.value,
      brain_result: JSON.parse(JSON.stringify(parsed.data)) as Record<string, unknown>,
      raw_model_output: raw,
      model: requestConfig.model,
      top_k: requestConfig.top_k ?? null,
      temperature: requestConfig.temperature,
      eval_mode: evalMode,
      evaluated_models: evalDetail.evaluated_models ?? [],
    })

    await loadBrainHistory()
    selectedBrainId.value = saved.id
    historyTab.value = 'brain'
    streaming.value = false
    ElMessage.success('智脑分析完成并已保存')
  } catch (error) {
    streaming.value = false
    streamPanelActive.value = false
    if (error instanceof DOMException && error.name === 'AbortError') {
      ElMessage.error(`智脑分析超时（连续 ${timeoutSeconds}s 无数据），请重试`)
    } else {
      ElMessage.error(error instanceof Error ? error.message : '智脑分析失败')
    }
  } finally {
    streamAbort = null
    analyzing.value = false
  }
}

onMounted(async () => {
  syncWithRegistry()
  await loadRpHistoryList()
})

onUnmounted(() => {
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
                {{ (row as RpHistorySummary).model_count }}
              </template>
            </el-table-column>
        </el-table>
        <p v-if="!rpHistoryLoading && rpHistoryList.length === 0" class="list-hint">
          暂无历史，请先在 RP 测试页运行测试
        </p>

        <el-tabs v-model="historyTab" class="history-tabs" stretch>
          <el-tab-pane label="测评历史" name="eval">
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
            <el-table
              v-loading="evalHistoryLoading"
              :data="evalHistory"
              highlight-current-row
              class="eval-table"
              size="small"
              empty-text="暂无测评"
              @row-click="onEvalRowClick"
            >
              <el-table-column label="时间" min-width="72">
                <template #default="{ row }">
                  {{ formatHistoryTime(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="SP版本" min-width="72" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ formatEvalPromptVersions(row as RpEvalSummary) }}
                </template>
              </el-table-column>
              <el-table-column label="被测" min-width="52" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ formatEvaluatedModels(row as RpEvalSummary) }}
                </template>
              </el-table-column>
              <el-table-column label="分" width="32" prop="overall_score" />
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="智脑历史" name="brain">
            <div class="sub-panel-title sub-panel-title-row tab-pane-toolbar">
              <span />
              <el-button
                size="small"
                type="danger"
                plain
                :disabled="!selectedBrainId || historyTab !== 'brain'"
                @click="removeBrainRecord"
              >
                删除
              </el-button>
            </div>
            <el-table
              v-loading="brainHistoryLoading"
              :data="brainHistory"
              highlight-current-row
              class="eval-table"
              size="small"
              empty-text="暂无智脑记录"
              @row-click="onBrainRowClick"
            >
              <el-table-column label="时间" min-width="72">
                <template #default="{ row }">
                  {{ formatHistoryTime(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="SP版本" min-width="72" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ formatBrainPromptVersions(row as BrainAnalysisSummary) }}
                </template>
              </el-table-column>
              <el-table-column label="建议" min-width="64">
                <template #default="{ row }">
                  {{ brainRecommendationLabel(row.overall) }}
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </AppPanel>
    </template>

    <template #center>
      <AppPanel title="编辑智脑 SP">
        <template #actions>
          <el-button size="small" @click="handleResetPrompt">恢复默认</el-button>
        </template>
        <el-empty
          v-if="!selectedEvalId && !selectedBrainSummary"
          description="请选择测评或智脑历史"
        />
        <el-form
          v-else
          label-width="88px"
          class="edit-form"
        >
            <el-form-item label="角色">
              <el-input
                :model-value="
                  selectedEvalDetail?.role_name ?? selectedBrainSummary?.role_name ?? '—'
                "
                disabled
              />
            </el-form-item>
            <el-form-item v-if="selectedBrainSummary" label="关联测评">
              <el-input :model-value="linkedEvalLabel" disabled />
            </el-form-item>
            <el-form-item label="被测 SP">
              <el-input
                :model-value="
                  selectedEvalSummary
                    ? formatEvalPromptVersions(selectedEvalSummary)
                    : selectedBrainSummary
                      ? formatBrainPromptVersions(selectedBrainSummary)
                      : '—'
                "
                disabled
              />
            </el-form-item>
            <el-form-item v-if="selectedEvalDetail && historyTab === 'eval'" label="测评模式">
              <el-input :model-value="selectedEvalModeLabel" disabled />
            </el-form-item>
            <el-form-item
              v-if="selectedEvalDetail && historyTab === 'eval'"
              label="被测模型"
            >
              <el-input :model-value="selectedEvaluatedModelsLabel" disabled />
            </el-form-item>
            <el-form-item
              v-if="selectedVersionKindLines.length > 0 && historyTab === 'eval'"
              label="版本类型"
            >
              <el-input :model-value="selectedVersionKindLines.join('\n')" type="textarea" disabled />
            </el-form-item>
            <el-form-item v-if="selectedEvalSummary" label="测评分">
              <el-input
                :model-value="`${selectedEvalSummary.overall_score} / 置信 ${formatConfidence(selectedEvalSummary.overall_confidence)}`"
                disabled
              />
            </el-form-item>
            <el-form-item v-if="selectedBrainSummary && historyTab === 'brain'" label="智脑建议">
              <el-input
                :model-value="brainRecommendationLabel(selectedBrainSummary.overall)"
                disabled
              />
            </el-form-item>
          <el-form-item label="智脑 SP" class="content-item">
            <el-input
              v-model="brainSystemPrompt"
              type="textarea"
              class="content-editor"
              placeholder="智脑分析用 System Prompt"
            />
          </el-form-item>
        </el-form>
      </AppPanel>
    </template>

    <template #right>
      <AppPanel title="智脑分析" title-class="panel-title-with-picker">
        <template #title>
          <span>智脑分析</span>
          <ApiRuntimePicker scope="brain" />
        </template>
        <div
          class="test-panel-body"
          :class="{ 'test-panel-body--preview': viewingBrainRecord || runtimeParamsHidden }"
        >
          <Transition name="params-collapse">
            <el-form
              v-if="!viewingBrainRecord && !runtimeParamsHidden"
              label-width="88px"
              class="test-form"
            >
              <RuntimeParamsFields
                :temperature="runtime.temperature"
                :top-k="runtime.top_k"
                @update:temperature="runtime.temperature = $event"
                @update:top-k="runtime.top_k = $event"
              />
              <el-form-item label=" " class="action-row">
                <el-button
                  type="primary"
                  :loading="analyzing"
                  :disabled="!canRunBrain"
                  @click="handleRunBrain"
                >
                  开始分析
                </el-button>
              </el-form-item>
            </el-form>
          </Transition>

          <div v-if="streamPanelActive || currentParsed" class="result-block">
            <div class="result-title-row">
              <span class="result-title">
                {{
                  streaming
                    ? '智脑分析生成中'
                    : viewingBrainRecord && selectedBrainId
                      ? `智脑记录 #${selectedBrainId}`
                      : '版本更迭建议'
                }}
              </span>
              <div
                v-if="viewingBrainRecord && (brainRecordTemperature !== null || brainRecordTopK !== null)"
                class="result-meta-chips"
              >
                <span
                  v-if="brainRecordTemperature !== null"
                  class="record-meta-chip"
                >
                  <span class="record-meta-label">temperature</span>
                  <span class="record-meta-value">{{ brainRecordTemperature }}</span>
                </span>
                <span v-if="brainRecordTopK !== null" class="record-meta-chip">
                  <span class="record-meta-label">top_k</span>
                  <span class="record-meta-value">{{ brainRecordTopK }}</span>
                </span>
              </div>
              <el-button
                v-else-if="runtimeParamsHidden && !streaming && !analyzing"
                link
                type="primary"
                size="small"
                @click="showRuntimeParamsAgain"
              >
                重新分析
              </el-button>
            </div>
            <StreamResultPanel
              v-if="streamPanelActive"
              class="result-scroll"
              :streaming="streaming"
              :content="currentRaw"
              :reasoning="currentReasoning"
            >
              <BrainResultView v-if="currentParsed" :parsed="currentParsed" />
            </StreamResultPanel>
            <el-scrollbar v-else class="result-scroll">
              <BrainResultView v-if="currentParsed" :parsed="currentParsed" />
            </el-scrollbar>
          </div>
          <el-empty
            v-else-if="currentRaw"
            class="result-empty"
            :description="`输出无法解析为 JSON，请检查智脑 SP 或模型能力`"
            :image-size="48"
          />
          <el-empty
            v-else
            class="result-empty"
            description="在「测评历史」选记录后分析，或在「智脑历史」查看已保存建议"
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
  min-height: 200px;
}

.action-row :deep(.el-form-item__content) {
  justify-content: flex-end;
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
  max-height: 140px;
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
  max-height: 140px;
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
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
  min-width: 0;
}

.result-title {
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}

.result-meta-chips {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
  min-width: 0;
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

.tab-pane-toolbar {
  border-top: none;
  min-height: 36px;
}
</style>
