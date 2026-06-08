<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getChatQaConversation,
  getRpHistoryDetail,
  listChatQaConversations,
  listRpHistory,
  type ChatQaConversationDetail,
  type ChatQaConversationSummary,
  type RpHistoryDetail,
  type RpHistoryRunMeta,
  type RpHistorySummary,
} from '../api'
import ChatQaBubble from '../components/ChatQaBubble.vue'
import JsonVisualViewer from '../components/JsonVisualViewer.vue'
import AdaptiveTabs from '../components/AdaptiveTabs.vue'

const leftTabItems = [
  { label: '对话问答', name: 'chat' },
  { label: '历史RP效果', name: 'history' },
]
const leftTab = ref<'chat' | 'history'>('chat')

const chatConversations = ref<ChatQaConversationSummary[]>([])
const selectedConversationKey = ref<string | null>(null)
const selectedConversation = ref<ChatQaConversationDetail | null>(null)
const filterUserId = ref('')
const filterRoleId = ref('')
const filterRoleName = ref('')
const chatLoading = ref(false)
const jsonExpanded = ref<string[]>([])

const rpHistoryList = ref<RpHistorySummary[]>([])
const selectedHistoryKey = ref<string | null>(null)
const rpHistoryDetail = ref<RpHistoryDetail | null>(null)
const selectedHistoryModel = ref('')
const historyLoading = ref(false)
const historyDetailLoading = ref(false)

const historyModelDetail = computed(() => {
  const base = rpHistoryDetail.value
  if (!base || !selectedHistoryModel.value) return null
  const run = base.model_runs.find((item) => item.model === selectedHistoryModel.value)
  if (!run) return null
  return {
    ...base,
    compress: run.compress,
    merge: run.merge,
    compress_segments: run.compress_segments ?? [],
    merge_results: run.merge_results ?? [],
    compress_run: run.compress_run,
    merge_run: run.merge_run,
  }
})

const chatTurns = computed(() =>
  (selectedConversation.value?.messages ?? []).map((msg) => ({
    question: msg.question,
    answer: msg.answer,
  })),
)

const chatJsonPreview = computed(() =>
  selectedConversation.value ? JSON.stringify(selectedConversation.value, null, 2) : '',
)

async function loadChatList() {
  chatLoading.value = true
  try {
    chatConversations.value = await listChatQaConversations({
      user_id: filterUserId.value || undefined,
      role_id: filterRoleId.value || undefined,
      role_name: filterRoleName.value || undefined,
    })
    if (chatConversations.value.length === 0) {
      selectedConversationKey.value = null
      selectedConversation.value = null
      return
    }
    const currentKey = selectedConversationKey.value
    const stillExists =
      currentKey && chatConversations.value.some((r) => r.conversation_key === currentKey)
    if (!stillExists) {
      void selectConversation(chatConversations.value[0])
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载对话列表失败')
  } finally {
    chatLoading.value = false
  }
}

async function selectConversation(row: ChatQaConversationSummary) {
  selectedConversationKey.value = row.conversation_key
  try {
    selectedConversation.value = await getChatQaConversation({
      user_id: row.user_id,
      role_id: row.role_id,
      app_name: row.app_name,
    })
  } catch (error) {
    selectedConversation.value = null
    ElMessage.error(error instanceof Error ? error.message : '加载对话详情失败')
  }
}

function onChatRowClick(row: ChatQaConversationSummary) {
  void selectConversation(row)
}

async function loadRpHistory() {
  historyLoading.value = true
  try {
    rpHistoryList.value = await listRpHistory({
      user_id: filterUserId.value || undefined,
      role_id: filterRoleId.value || undefined,
      role_name: filterRoleName.value || undefined,
    })
    if (rpHistoryList.value.length === 0) {
      selectedHistoryKey.value = null
      rpHistoryDetail.value = null
      return
    }
    const currentKey = selectedHistoryKey.value
    const stillExists =
      currentKey && rpHistoryList.value.some((r) => r.history_key === currentKey)
    if (!stillExists) {
      void selectRpHistory(rpHistoryList.value[0])
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载历史 RP 效果失败')
  } finally {
    historyLoading.value = false
  }
}

async function selectRpHistory(row: RpHistorySummary) {
  selectedHistoryKey.value = row.history_key
  rpHistoryDetail.value = null
  historyDetailLoading.value = true
  try {
    rpHistoryDetail.value = await getRpHistoryDetail({
      user_id: row.user_id,
      role_id: row.role_id,
      app_name: row.app_name,
      run_group_id: row.run_group_id,
    })
    selectedHistoryModel.value = rpHistoryDetail.value.model_runs[0]?.model ?? ''
  } catch (error) {
    rpHistoryDetail.value = null
    selectedHistoryModel.value = ''
    ElMessage.error(error instanceof Error ? error.message : '加载历史 RP 详情失败')
  } finally {
    historyDetailLoading.value = false
  }
}

function onHistoryRowClick(row: RpHistorySummary) {
  void selectRpHistory(row)
}

function formatRunMeta(run: RpHistoryRunMeta | null | undefined): string {
  if (!run || (!run.prompt_version && !run.model)) {
    return '暂无测试参数记录（请重新运行测试后保存）'
  }
  const topK = run.top_k == null ? '—' : String(run.top_k)
  return `SP 版本 ${run.prompt_version || '—'} · 模型 ${run.model || '—'} · top_k ${topK} · 温度 ${run.temperature}`
}

function searchHistory() {
  void loadRpHistory()
}

onMounted(async () => {
  await Promise.all([loadChatList(), loadRpHistory()])
})
</script>

<template>
  <el-card class="page-card" shadow="never">
    <el-row :gutter="16" class="full-height">
      <el-col :span="6" class="full-height">
        <div class="panel">
          <div class="panel-title">测试用例列表</div>
          <AdaptiveTabs v-model="leftTab" :items="leftTabItems" layout="stretch" />

          <div v-if="leftTab === 'chat'" class="filters">
            <el-input
              v-model="filterUserId"
              placeholder="模糊搜索用户 id"
              clearable
              size="small"
              @keyup.enter="loadChatList"
              @clear="loadChatList"
            />
            <el-input
              v-model="filterRoleId"
              placeholder="模糊搜索角色 id"
              clearable
              size="small"
              @keyup.enter="loadChatList"
              @clear="loadChatList"
            />
            <el-input
              v-model="filterRoleName"
              placeholder="模糊搜索角色昵称"
              clearable
              size="small"
              @keyup.enter="loadChatList"
              @clear="loadChatList"
            />
            <el-button size="small" @click="loadChatList">查询</el-button>
          </div>

          <div v-else class="filters">
            <el-input
              v-model="filterUserId"
              placeholder="模糊搜索用户 id"
              clearable
              size="small"
              @keyup.enter="searchHistory"
              @clear="searchHistory"
            />
            <el-input
              v-model="filterRoleId"
              placeholder="模糊搜索角色 id"
              clearable
              size="small"
              @keyup.enter="searchHistory"
              @clear="searchHistory"
            />
            <el-input
              v-model="filterRoleName"
              placeholder="模糊搜索角色昵称"
              clearable
              size="small"
              @keyup.enter="searchHistory"
              @clear="searchHistory"
            />
            <el-button size="small" @click="searchHistory">查询</el-button>
          </div>

          <el-table
            v-if="leftTab === 'chat'"
            v-loading="chatLoading"
            :data="chatConversations"
            highlight-current-row
            class="record-table"
            size="small"
            row-key="conversation_key"
            @row-click="onChatRowClick"
          >
            <el-table-column prop="user_id" label="用户 id" min-width="72" show-overflow-tooltip />
            <el-table-column prop="role_id" label="角色 id" min-width="64" show-overflow-tooltip />
            <el-table-column prop="role_name" label="昵称" min-width="64" show-overflow-tooltip />
            <el-table-column prop="app_name" label="App" min-width="56" show-overflow-tooltip />
            <el-table-column prop="message_count" label="轮数" width="48" align="center" />
          </el-table>

          <el-table
            v-else
            v-loading="historyLoading"
            :data="rpHistoryList"
            highlight-current-row
            class="record-table"
            size="small"
            row-key="history_key"
            @row-click="onHistoryRowClick"
          >
            <el-table-column prop="role_name" label="昵称" min-width="80" show-overflow-tooltip />
            <el-table-column prop="user_id" label="用户 id" min-width="72" show-overflow-tooltip />
            <el-table-column prop="prompt_version" label="SP" width="44" show-overflow-tooltip />
            <el-table-column label="模型" width="44" align="center" prop="model_count" />
            <el-table-column label="压缩" width="56" align="center">
              <template #default="{ row }">
                <el-tag :type="row.has_compress ? 'success' : 'info'" size="small">
                  {{ row.has_compress ? '有' : '无' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="合并" width="56" align="center">
              <template #default="{ row }">
                <el-tag :type="row.has_merge ? 'success' : 'info'" size="small">
                  {{ row.has_merge ? '有' : '无' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>

      <el-col :span="18" class="full-height">
        <div class="panel">
          <div class="panel-title">
            <span>{{ leftTab === 'chat' ? '对话详情' : '历史 RP 效果' }}</span>
          </div>

          <el-empty v-if="leftTab === 'chat' && !selectedConversation" description="请选择对话问答" />
          <div v-else-if="leftTab === 'chat' && selectedConversation" class="detail-body">
            <el-alert
              type="info"
              :closable="false"
              show-icon
              title="RP 测试页运行成功后，结果会自动写入「历史 RP 效果」"
              class="prompt-hint"
            />
            <div class="meta-tags">
              <el-tag size="small">用户 id: {{ selectedConversation.user_id }}</el-tag>
              <el-tag size="small" type="info">角色 id: {{ selectedConversation.role_id }}</el-tag>
              <el-tag size="small" type="success">昵称: {{ selectedConversation.role_name }}</el-tag>
              <el-tag v-if="selectedConversation.app_name" size="small" type="warning">
                {{ selectedConversation.app_name }}
              </el-tag>
              <el-tag size="small" type="info">共 {{ selectedConversation.message_count }} 轮</el-tag>
            </div>
            <ChatQaBubble :turns="chatTurns" />
            <el-collapse v-model="jsonExpanded">
              <el-collapse-item name="json" title="JSON 详情">
                <el-scrollbar max-height="280px">
                  <pre class="json-pre">{{ chatJsonPreview }}</pre>
                </el-scrollbar>
              </el-collapse-item>
            </el-collapse>
          </div>

          <el-empty
            v-else-if="leftTab === 'history' && !rpHistoryDetail"
            description="暂无历史 RP 效果（请在 RP 测试页运行测试）"
          />
          <div
            v-else-if="leftTab === 'history' && (rpHistoryDetail || historyDetailLoading)"
            v-loading="historyDetailLoading"
            class="detail-body history-body"
          >
            <template v-if="rpHistoryDetail">
              <div class="meta-tags">
                <el-tag size="small">昵称: {{ rpHistoryDetail.role_name }}</el-tag>
                <el-tag size="small" type="info">
                  用户 {{ rpHistoryDetail.user_id }} · 角色 {{ rpHistoryDetail.role_id }}
                </el-tag>
                <el-tag size="small" type="warning">
                  第 {{ rpHistoryDetail.round_start }}-{{ rpHistoryDetail.round_end }} 轮
                </el-tag>
                <el-tag size="small">SP: {{ rpHistoryDetail.prompt_version }}</el-tag>
              </div>
              <el-form-item v-if="rpHistoryDetail.model_runs.length > 0" label="模型" class="history-model-select">
                <el-select v-model="selectedHistoryModel" style="width: 100%">
                  <el-option
                    v-for="run in rpHistoryDetail.model_runs"
                    :key="run.model"
                    :label="run.model"
                    :value="run.model"
                  />
                </el-select>
              </el-form-item>
              <p class="history-hint">
                Compress 按段存储（段 1: 1-10，段 2: 11-21…）；Merge 按段窗口存储（如 1-4 段、1-3 段各一条）。
                链路测试按每 4 段批量合并；尾批不足 4 段时强制合并。单步合并从已保存 compress 段中连续选取 1-4 段。
              </p>
              <div v-if="historyModelDetail" class="history-panels">
                <div class="json-panel">
                  <div class="json-panel-title">Compress 段</div>
                  <p class="run-meta">{{ formatRunMeta(historyModelDetail.compress_run) }}</p>
                  <el-scrollbar class="json-panel-scroll">
                    <template v-if="historyModelDetail.compress_segments.length > 0">
                      <div
                        v-for="segment in historyModelDetail.compress_segments"
                        :key="`${selectedHistoryKey}-${selectedHistoryModel}-compress-${segment.id}`"
                        class="history-segment-block"
                      >
                        <div class="history-segment-title">
                          段 {{ segment.segment_index }} · 第 {{ segment.round_start }}-{{ segment.round_end }} 轮
                        </div>
                        <JsonVisualViewer :data="segment.expected_result" />
                      </div>
                    </template>
                    <el-empty v-else description="暂无 Compress 结果" :image-size="64" />
                  </el-scrollbar>
                </div>
                <div class="json-panel">
                  <div class="json-panel-title">Merge 记录</div>
                  <p class="run-meta">{{ formatRunMeta(historyModelDetail.merge_run) }}</p>
                  <el-scrollbar class="json-panel-scroll">
                    <template v-if="historyModelDetail.merge_results.length > 0">
                      <div
                        v-for="merge in historyModelDetail.merge_results"
                        :key="`${selectedHistoryKey}-${selectedHistoryModel}-merge-${merge.id}`"
                        class="history-segment-block"
                      >
                        <div class="history-segment-title">
                          段 {{ merge.merge_segment_start }}-{{ merge.merge_segment_end }} · 第 {{ merge.round_start }}-{{ merge.round_end }} 轮
                        </div>
                        <JsonVisualViewer :data="merge.expected_result" />
                      </div>
                    </template>
                    <el-empty v-else description="暂无 Merge 结果" :image-size="64" />
                  </el-scrollbar>
                </div>
              </div>
            </template>
          </div>
        </div>
      </el-col>
    </el-row>
  </el-card>
</template>

<style scoped>
.page-card {
  border: none;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.page-card :deep(.el-card__body) {
  flex: 1;
  height: 100%;
  min-height: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-card :deep(.full-height.el-row) {
  flex: 1;
  min-height: 0;
  width: 100%;
}

.page-card :deep(.full-height.el-col) {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  height: 100%;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
}

.panel-title {
  flex-shrink: 0;
  padding: 12px 14px;
  font-weight: 600;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
}

.filters {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
}

.record-table {
  flex: 1;
  min-height: 0;
}

.detail-body {
  flex: 1;
  min-height: 0;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
}

.history-body {
  overflow: hidden;
}

.history-hint {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.6;
  color: #909399;
}

.history-hint code {
  font-size: 11px;
  color: #606266;
}

.meta-tags {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.history-panels {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.json-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  background: #fafafa;
}

.json-panel-title {
  flex-shrink: 0;
  padding: 10px 12px;
  font-weight: 600;
  font-size: 14px;
  border-bottom: 1px solid #ebeef5;
  background: #fff;
}

.run-meta {
  flex-shrink: 0;
  margin: 0;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1.5;
  color: #606266;
  background: #f5f7fa;
  border-bottom: 1px solid #ebeef5;
}

.history-segment-block + .history-segment-block {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #ebeef5;
}

.history-segment-title {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #303133;
}

.json-panel-scroll {
  flex: 1;
  min-height: 0;
  padding: 12px;
}

.json-panel-scroll :deep(.el-scrollbar) {
  height: 100%;
}

.json-panel-scroll :deep(.el-scrollbar__wrap) {
  overflow-x: hidden;
}

.json-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
}

.prompt-hint {
  margin-bottom: 4px;
}
</style>
