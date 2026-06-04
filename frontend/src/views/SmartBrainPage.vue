<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getRpEval,
  getRpHistoryDetail,
  listRpEvaluations,
  listRpHistory,
  listVersions,
  runChatCompletion,
  type RpEvalDetail,
  type RpEvalSummary,
  type RpHistoryDetail,
  type RpHistorySummary,
} from '../api'
import ApiRuntimePicker from '../components/ApiRuntimePicker.vue'
import BrainResultView from '../components/BrainResultView.vue'
import ThreeColumnPage from '../components/layout/ThreeColumnPage.vue'
import AppPanel from '../components/layout/AppPanel.vue'
import FilterBar from '../components/layout/FilterBar.vue'
import RuntimeParamsFields from '../components/RuntimeParamsFields.vue'
import { usePageRuntime } from '../composables/usePageRuntime'
import { DEEPSEEK_JSON_OUTPUT_EXTRA } from '../utils/apiProfileStorage'
import { buildBrainUserPayload } from '../utils/brainPayload'
import {
  loadBrainSystemPrompt,
  resetBrainSystemPrompt,
  saveBrainSystemPrompt,
} from '../utils/brainPromptStorage'
import { parseBrainJson, type BrainParsed } from '../utils/parseBrainJson'
import { formatEvalPromptVersions } from '../utils/rpEvalFormat'
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
const evalHistory = ref<RpEvalSummary[]>([])
const evalHistoryLoading = ref(false)
const selectedEvalId = ref<number | null>(null)
const selectedEvalDetail = ref<RpEvalDetail | null>(null)
const currentRaw = ref('')
const currentParsed = ref<BrainParsed | null>(null)

const selectedEvalSummary = computed(
  () => evalHistory.value.find((item) => item.id === selectedEvalId.value) ?? null,
)

const canRunBrain = computed(
  () => Boolean(selectedEvalId.value && selectedEvalDetail.value && resolvedRequest.value),
)

function rpHistoryFlags(row: RpHistorySummary): string {
  return [row.has_compress ? 'C' : '', row.has_merge ? 'M' : ''].filter(Boolean).join('') || '—'
}

watch(brainSystemPrompt, (text) => {
  saveBrainSystemPrompt(text)
})

watch(selectedRpHistoryKey, () => {
  selectedEvalId.value = null
  selectedEvalDetail.value = null
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
  const summary = rpHistoryList.value.find((item) => item.conversation_key === key)
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
  brainSystemPrompt.value = resetBrainSystemPrompt()
  ElMessage.success('已恢复默认智脑 SP')
}

async function selectEvalRow(row: RpEvalSummary) {
  selectedEvalId.value = row.id
  currentRaw.value = ''
  currentParsed.value = null
  try {
    selectedEvalDetail.value = await getRpEval(row.id)
  } catch (error) {
    selectedEvalDetail.value = null
    ElMessage.error(error instanceof Error ? error.message : '加载测评详情失败')
  }
}

function onEvalRowClick(row: RpEvalSummary) {
  void selectEvalRow(row)
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
  analyzing.value = true
  currentRaw.value = ''
  currentParsed.value = null

  try {
    const versionCatalog = await listVersions()
    const userContent = await buildBrainUserPayload({ evalDetail, versionCatalog })
    const extra = {
      ...(requestConfig.extra_body ?? {}),
      ...DEEPSEEK_JSON_OUTPUT_EXTRA,
    }

    const resp = await runChatCompletion({
      base_url: requestConfig.base_url,
      api_key: requestConfig.api_key,
      model: requestConfig.model,
      temperature: requestConfig.temperature,
      top_k: requestConfig.top_k ?? null,
      extra_body: extra,
      system_prompt: brainSystemPrompt.value,
      user_content: userContent,
    })

    const raw = resp.raw_content || resp.error || resp.raw_text || ''
    currentRaw.value = raw

    if (resp.status !== 200) {
      ElMessage.error(`智脑请求失败: HTTP ${resp.status}`)
      return
    }

    const parsed = parseBrainJson(raw)
    if (!parsed.ok || !parsed.data) {
      ElMessage.warning(parsed.error || '智脑 JSON 解析失败')
      return
    }
    currentParsed.value = parsed.data
    ElMessage.success('智脑分析完成')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '智脑分析失败')
  } finally {
    analyzing.value = false
  }
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
          <el-table-column label="时间" min-width="80">
            <template #default="{ row }">
              {{ formatHistoryTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="SP版本" min-width="80" show-overflow-tooltip>
            <template #default="{ row }">
              {{ formatEvalPromptVersions(row as RpEvalSummary) }}
            </template>
          </el-table-column>
          <el-table-column label="分" width="36" prop="overall_score" />
          <el-table-column label="置信" width="48">
            <template #default="{ row }">
              {{ formatConfidence(row.overall_confidence) }}
            </template>
          </el-table-column>
        </el-table>
      </AppPanel>
    </template>

    <template #center>
      <AppPanel title="编辑智脑 SP">
        <template #actions>
          <el-button size="small" @click="handleResetPrompt">恢复默认</el-button>
        </template>
        <el-empty v-if="!selectedEvalId" description="请选择一条测评历史" />
        <el-form v-else label-width="88px" class="edit-form">
          <el-form-item label="角色">
            <el-input :model-value="selectedEvalDetail?.role_name ?? '—'" disabled />
          </el-form-item>
          <el-form-item label="被测 SP">
            <el-input
              :model-value="
                selectedEvalSummary ? formatEvalPromptVersions(selectedEvalSummary) : '—'
              "
              disabled
            />
          </el-form-item>
          <el-form-item label="测评分">
            <el-input
              :model-value="
                selectedEvalSummary
                  ? `${selectedEvalSummary.overall_score} / 置信 ${formatConfidence(selectedEvalSummary.overall_confidence)}`
                  : '—'
              "
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
        <div class="test-panel-body">
          <el-form label-width="88px" class="test-form">
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

          <div v-if="currentParsed" class="result-block">
            <div class="result-title">版本更迭建议</div>
            <el-scrollbar class="result-scroll">
              <BrainResultView :parsed="currentParsed" />
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
            description="选择测评历史后点击「开始分析」"
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

.result-block {
  flex: 1;
  min-height: 0;
  padding: 0 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-title {
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
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
