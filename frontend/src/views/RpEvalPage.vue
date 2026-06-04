<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getChatQaConversation,
  getRpEval,
  getRpHistoryDetail,
  listRpEvaluations,
  listRpHistory,
  runChatCompletion,
  saveRpEval,
  type RpEvalSummary,
  type RpHistoryDetail,
  type RpHistorySummary,
} from '../api'
import ApiRuntimePicker from '../components/ApiRuntimePicker.vue'
import RpEvalResultView from '../components/RpEvalResultView.vue'
import ThreeColumnPage from '../components/layout/ThreeColumnPage.vue'
import AppPanel from '../components/layout/AppPanel.vue'
import FilterBar from '../components/layout/FilterBar.vue'
import RuntimeParamsFields from '../components/RuntimeParamsFields.vue'
import { formatConfidence, formatHistoryTime } from '../utils/format'
import { formatEvalPromptVersions } from '../utils/rpEvalFormat'
import { usePageRuntime } from '../composables/usePageRuntime'
import { buildRpEvalUserContent } from '../utils/rpEvalPayload'
import { parseRpEvalJson, type RpEvalParsed } from '../utils/parseRpEvalJson'
import {
  loadRpEvalSystemPrompt,
  resetRpEvalSystemPrompt,
  saveRpEvalSystemPrompt,
} from '../utils/rpEvalPromptStorage'

const evalRuntime = usePageRuntime('eval')
const { runtime, resolvedRequest, syncWithRegistry } = evalRuntime

const rpHistoryList = ref<RpHistorySummary[]>([])
const rpHistoryLoading = ref(false)
const filterRoleName = ref('')
const selectedRpHistoryKey = ref('')
const rpHistoryDetail = ref<RpHistoryDetail | null>(null)

const evalSystemPrompt = ref(loadRpEvalSystemPrompt())
const evaluating = ref(false)
const evalHistory = ref<RpEvalSummary[]>([])
const evalHistoryLoading = ref(false)
const selectedEvalId = ref<number | null>(null)
const currentRaw = ref('')
const currentParsed = ref<RpEvalParsed | null>(null)

const selectedRpHistorySummary = computed(
  () =>
    rpHistoryList.value.find((item) => item.conversation_key === selectedRpHistoryKey.value) ??
    null,
)

const canRunEval = computed(() => {
  if (!selectedRpHistoryKey.value || !rpHistoryDetail.value) return false
  const d = rpHistoryDetail.value
  return Boolean(d.compress || d.merge) && Boolean(resolvedRequest.value)
})

function rpHistoryFlags(row: RpHistorySummary): string {
  return [row.has_compress ? 'C' : '', row.has_merge ? 'M' : ''].filter(Boolean).join('') || '—'
}

const selectedEvalSummary = computed(
  () => evalHistory.value.find((item) => item.id === selectedEvalId.value) ?? null,
)

watch(evalSystemPrompt, (text) => {
  saveRpEvalSystemPrompt(text)
})

watch(selectedRpHistoryKey, () => {
  selectedEvalId.value = null
  currentRaw.value = ''
  currentParsed.value = null
  void syncRpHistorySelection(selectedRpHistoryKey.value)
  void loadEvalHistory()
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
      !rpHistoryList.value.some((item) => item.conversation_key === selectedRpHistoryKey.value)
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
  selectedRpHistoryKey.value = row.conversation_key
}

function onRpHistoryRowClick(row: { conversation_key?: string }) {
  selectRpHistory(row as RpHistorySummary)
}

async function syncRpHistorySelection(key: string) {
  if (!key) {
    rpHistoryDetail.value = null
    return
  }
  const summary = selectedRpHistorySummary.value
  if (!summary) return
  try {
    rpHistoryDetail.value = await getRpHistoryDetail({
      user_id: summary.user_id,
      role_id: summary.role_id,
      app_name: summary.app_name,
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

function handleResetPrompt() {
  evalSystemPrompt.value = resetRpEvalSystemPrompt()
  ElMessage.success('已恢复默认测评 SP')
}

async function handleRunEval() {
  if (!canRunEval.value) {
    if (!selectedRpHistoryKey.value) {
      ElMessage.warning('请先在左侧选择 RP 历史')
    } else if (!rpHistoryDetail.value?.compress && !rpHistoryDetail.value?.merge) {
      ElMessage.warning('该 RP 历史缺少 Compress/Merge 结果')
    } else {
      ElMessage.warning('请先在 API 配置页填写有效 API')
    }
    return
  }

  const detail = rpHistoryDetail.value!
  const requestConfig = resolvedRequest.value!
  evaluating.value = true
  currentRaw.value = ''
  currentParsed.value = null
  selectedEvalId.value = null

  try {
    const conv = await getChatQaConversation({
      user_id: detail.user_id,
      role_id: detail.role_id,
      app_name: detail.app_name,
    })
    const userContent = buildRpEvalUserContent({
      messages: conv.messages,
      detail,
    })

    const resp = await runChatCompletion({
      base_url: requestConfig.base_url,
      api_key: requestConfig.api_key,
      model: requestConfig.model,
      temperature: requestConfig.temperature,
      top_k: requestConfig.top_k ?? null,
      extra_body: requestConfig.extra_body,
      system_prompt: evalSystemPrompt.value,
      user_content: userContent,
    })

    const raw = resp.raw_content || resp.error || resp.raw_text || ''
    currentRaw.value = raw

    if (resp.status !== 200) {
      ElMessage.error(`测评请求失败: HTTP ${resp.status}`)
      return
    }

    const parsed = parseRpEvalJson(raw)
    if (!parsed.ok || !parsed.data) {
      ElMessage.warning(parsed.error || '测评 JSON 解析失败，未入库')
      return
    }
    currentParsed.value = parsed.data

    const saved = await saveRpEval({
      user_id: detail.user_id,
      role_id: detail.role_id,
      app_name: detail.app_name,
      role_name: detail.role_name,
      round_start: detail.round_start,
      round_end: detail.round_end,
      has_compress: Boolean(detail.compress),
      has_merge: Boolean(detail.merge),
      compress_prompt_version: detail.compress_run?.prompt_version ?? '',
      merge_prompt_version: detail.merge_run?.prompt_version ?? '',
      eval_system_prompt: evalSystemPrompt.value,
      eval_result: JSON.parse(JSON.stringify(parsed.data)) as Record<string, unknown>,
      raw_model_output: raw,
      model: requestConfig.model,
      top_k: requestConfig.top_k ?? null,
      temperature: requestConfig.temperature,
    })

    selectedEvalId.value = saved.id
    await loadEvalHistory()
    ElMessage.success('测评完成并已保存')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '测评失败')
  } finally {
    evaluating.value = false
  }
}

async function selectEvalRow(row: RpEvalSummary) {
  selectedEvalId.value = row.id
  try {
    const detail = await getRpEval(row.id)
    currentRaw.value = detail.raw_model_output
    const parsed = parseRpEvalJson(JSON.stringify(detail.eval_result))
    currentParsed.value = parsed.ok ? parsed.data ?? null : null
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载测评详情失败')
  }
}

function onEvalRowClick(row: RpEvalSummary) {
  void selectEvalRow(row)
}

onMounted(async () => {
  syncWithRegistry()
  await loadRpHistoryList()
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
            row-key="conversation_key"
            @row-click="onRpHistoryRowClick"
          >
            <el-table-column prop="role_name" label="角色" min-width="72" show-overflow-tooltip />
            <el-table-column label="轮次" width="72">
              <template #default="{ row }">
                {{ row.round_start }}-{{ row.round_end }}
              </template>
            </el-table-column>
            <el-table-column label="类型" width="48">
              <template #default="{ row }">
                {{ rpHistoryFlags(row as RpHistorySummary) }}
              </template>
            </el-table-column>
          </el-table>
          <p v-if="!rpHistoryLoading && rpHistoryList.length === 0" class="list-hint">
            暂无历史，请先在 RP 测试页运行测试
          </p>

          <div class="sub-panel-title">测评历史</div>
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
            <el-table-column label="分" width="40" prop="overall_score" />
            <el-table-column label="置信" width="52">
              <template #default="{ row }">
                {{ formatConfidence(row.overall_confidence) }}
              </template>
            </el-table-column>
          </el-table>
      </AppPanel>
    </template>

    <template #center>
      <AppPanel title="编辑测评 SP">
        <template #actions>
          <el-button size="small" @click="handleResetPrompt">恢复默认</el-button>
        </template>
          <el-empty v-if="!selectedRpHistoryKey" description="请选择 RP 历史" />
          <el-form v-else label-width="88px" class="edit-form">
            <el-form-item label="角色">
              <el-input :model-value="rpHistoryDetail?.role_name ?? '—'" disabled />
            </el-form-item>
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
            <el-form-item label="被测 SP">
              <el-input
                :model-value="
                  rpHistoryDetail
                    ? [
                        rpHistoryDetail.compress_run?.prompt_version
                          ? `Compress: ${rpHistoryDetail.compress_run.prompt_version}`
                          : '',
                        rpHistoryDetail.merge_run?.prompt_version
                          ? `Merge: ${rpHistoryDetail.merge_run.prompt_version}`
                          : '',
                      ]
                        .filter(Boolean)
                        .join(' · ') || '—'
                    : '—'
                "
                disabled
              />
            </el-form-item>
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
        <div class="test-panel-body">
          <el-form label-width="88px" class="test-form">
            <RuntimeParamsFields
              :temperature="runtime.temperature"
              :top-k="runtime.top_k"
              @update:temperature="runtime.temperature = $event"
              @update:top-k="runtime.top_k = $event"
            />
            <el-form-item label=" " class="top-k-row">
              <div class="top-k-row-inner">
                <el-button
                  type="primary"
                  :loading="evaluating"
                  :disabled="!canRunEval"
                  @click="handleRunEval"
                >
                  开始测评
                </el-button>
              </div>
            </el-form-item>
          </el-form>

          <div v-if="currentRaw || currentParsed" class="result-block">
            <div class="result-title">
              <span>{{
                selectedEvalId ? `测评结果 #${selectedEvalId}` : '本次测评结果'
              }}</span>
              <span
                v-if="
                  (selectedEvalSummary &&
                    formatEvalPromptVersions(selectedEvalSummary) !== '—') ||
                  (!selectedEvalId &&
                    rpHistoryDetail &&
                    [
                      rpHistoryDetail.compress_run?.prompt_version
                        ? `C:${rpHistoryDetail.compress_run.prompt_version}`
                        : '',
                      rpHistoryDetail.merge_run?.prompt_version
                        ? `M:${rpHistoryDetail.merge_run.prompt_version}`
                        : '',
                    ]
                      .filter(Boolean)
                      .join(' '))
                "
                class="result-prompt-versions"
              >
                {{
                  selectedEvalSummary
                    ? formatEvalPromptVersions(selectedEvalSummary)
                    : [
                        rpHistoryDetail?.compress_run?.prompt_version
                          ? `C:${rpHistoryDetail.compress_run.prompt_version}`
                          : '',
                        rpHistoryDetail?.merge_run?.prompt_version
                          ? `M:${rpHistoryDetail.merge_run.prompt_version}`
                          : '',
                      ]
                        .filter(Boolean)
                        .join(' ')
                }}
              </span>
            </div>
            <el-scrollbar class="result-scroll">
              <RpEvalResultView :raw-content="currentRaw" :parsed="currentParsed" />
            </el-scrollbar>
          </div>
          <el-empty
            v-else
            class="result-empty"
            description="运行测评或点击左侧测评历史查看结果"
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

.top-k-row-inner {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.top-k-row-inner .el-button {
  margin-left: auto;
}

.result-block {
  flex: 1;
  min-height: 0;
  padding: 0 14px 14px;
}

.result-title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 13px;
  font-weight: 600;
}

.result-prompt-versions {
  font-size: 12px;
  font-weight: 500;
  color: #909399;
}

.result-scroll {
  flex: 1;
  min-height: 0;
}

.result-empty {
  flex: 1;
  padding: 12px;
}
</style>
