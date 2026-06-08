<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getChatQaConversation,
  listChatQaConversations,
  type ChatQaConversationDetail,
  type ChatQaConversationSummary,
} from '../api'
import ChatQaBubble from '../components/ChatQaBubble.vue'

const chatConversations = ref<ChatQaConversationSummary[]>([])
const selectedConversationKey = ref<string | null>(null)
const selectedConversation = ref<ChatQaConversationDetail | null>(null)
const filterUserId = ref('')
const filterRoleId = ref('')
const filterRoleName = ref('')
const chatLoading = ref(false)
const jsonExpanded = ref<string[]>([])

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

onMounted(() => {
  void loadChatList()
})
</script>

<template>
  <el-card class="page-card" shadow="never">
    <el-row :gutter="16" class="full-height">
      <el-col :span="6" class="full-height">
        <div class="panel">
          <div class="panel-title">测试用例列表</div>

          <div class="filters">
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

          <el-table
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
        </div>
      </el-col>

      <el-col :span="18" class="full-height">
        <div class="panel">
          <div class="panel-title">
            <span>对话详情</span>
          </div>

          <el-empty v-if="!selectedConversation" description="请选择对话问答" />
          <div v-else class="detail-body">
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

.meta-tags {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.json-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
}
</style>
