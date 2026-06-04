<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { formatApiDisplayUrl, useApiProfileRegistry } from '../composables/useApiProfileRegistry'
import {
  DEEPSEEK_JSON_OUTPUT_EXTRA,
  formatExtraBodyJson,
  normalizeExtraBody,
  parseExtraBodyJson,
  type ApiProfile,
} from '../utils/apiProfileStorage'

const {
  registry,
  configLoadedFromStorage,
  lastSavedAt,
  formatSavedTime,
  clearAllProfiles,
  addProfile,
  removeProfile,
  normalizeProfileBaseUrl,
  addModelToProfile,
  removeModelFromProfile,
  flushRegistrySave,
} = useApiProfileRegistry()

onBeforeUnmount(() => {
  flushRegistrySave()
})

const selectedProfileId = ref('')
const newModelInput = ref('')

const selectedProfile = computed(() =>
  registry.value.profiles.find((item) => item.id === selectedProfileId.value) ?? null,
)

watch(
  () => registry.value.profiles,
  (profiles) => {
    if (profiles.length === 0) return
    if (!selectedProfileId.value || !profiles.some((item) => item.id === selectedProfileId.value)) {
      selectedProfileId.value = profiles[0].id
    }
  },
  { immediate: true, deep: true },
)

function handleAddProfile() {
  const profile = addProfile()
  selectedProfileId.value = profile.id
}

function handleRemoveProfile() {
  if (!selectedProfile.value) return
  const id = selectedProfile.value.id
  removeProfile(id)
}

function handleAddModel() {
  if (!selectedProfile.value) return
  if (addModelToProfile(selectedProfile.value.id, newModelInput.value)) {
    newModelInput.value = ''
  }
}

function handleRemoveModel(model: string) {
  if (!selectedProfile.value) return
  removeModelFromProfile(selectedProfile.value.id, model)
}

function profileSummary(profile: { name: string; base_url: string }) {
  return `${profile.name} · ${formatApiDisplayUrl(profile.base_url)}`
}

const extraBodyText = ref('{}')
const extraBodyEditingProfileId = ref('')

watch(
  selectedProfile,
  (profile) => {
    if (!profile) {
      extraBodyText.value = '{}'
      extraBodyEditingProfileId.value = ''
      return
    }
    extraBodyEditingProfileId.value = profile.id
    extraBodyText.value = formatExtraBodyJson(profile.extra_body)
  },
  { immediate: true },
)

function applyExtraBodyFromText(profile: ApiProfile) {
  try {
    profile.extra_body = parseExtraBodyJson(extraBodyText.value)
    extraBodyText.value = formatExtraBodyJson(profile.extra_body)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'JSON 格式无效')
    extraBodyText.value = formatExtraBodyJson(profile.extra_body)
  }
}

function onExtraBodyBlur() {
  const profile = selectedProfile.value
  if (!profile || profile.id !== extraBodyEditingProfileId.value) return
  applyExtraBodyFromText(profile)
}

function fillDeepseekJsonOutput() {
  const profile = selectedProfile.value
  if (!profile) return
  profile.extra_body = {
    ...normalizeExtraBody(profile.extra_body),
    ...DEEPSEEK_JSON_OUTPUT_EXTRA,
  }
  extraBodyText.value = formatExtraBodyJson(profile.extra_body)
}
</script>

<template>
  <el-card class="page-card" shadow="never">
    <template #header>
      <div class="page-header">
        <span>API 配置</span>
        <el-tag v-if="configLoadedFromStorage" size="small" type="success">
          已本地保存{{ lastSavedAt ? ` · ${formatSavedTime(lastSavedAt)}` : '' }}
        </el-tag>
      </div>
    </template>

    <p class="storage-hint">
      统一管理 API 配置池与每个 API 下的 model 子池。RP 测试、RP 测评、破限页可各自切换 API 与 model；
      temperature / top_k 在各页面单独设置。每个 API 可配置<strong>额外请求体参数</strong>（如 DeepSeek
      <code>response_format</code>），在调用 Chat Completions 时合并进请求体。
    </p>

    <el-row :gutter="16" class="layout-row">
      <el-col :span="8">
        <div class="side-panel">
          <div class="side-panel-header">
            <span>API 配置池</span>
            <el-button size="small" type="primary" @click="handleAddProfile">新增</el-button>
          </div>
          <el-menu :default-active="selectedProfileId" class="profile-menu" @select="(id: string) => (selectedProfileId = id)">
            <el-menu-item v-for="item in registry.profiles" :key="item.id" :index="item.id">
              <div class="profile-menu-item">
                <span class="profile-name">{{ item.name }}</span>
                <span class="profile-host">{{ formatApiDisplayUrl(item.base_url) }}</span>
              </div>
            </el-menu-item>
          </el-menu>
        </div>
      </el-col>

      <el-col :span="16">
        <div v-if="selectedProfile" class="detail-panel">
          <div class="detail-header">
            <span>{{ profileSummary(selectedProfile) }}</span>
            <el-button
              size="small"
              type="danger"
              plain
              :disabled="registry.profiles.length <= 1"
              @click="handleRemoveProfile"
            >
              删除
            </el-button>
          </div>

          <el-form label-width="120px" class="config-form">
            <el-form-item label="名称">
              <el-input v-model="selectedProfile.name" placeholder="如 生产环境、本地调试" />
            </el-form-item>
            <el-form-item label="BASE_URL">
              <el-input
                v-model="selectedProfile.base_url"
                placeholder="如 http://host:3000，将自动补全 /v1/chat/completions"
                @blur="normalizeProfileBaseUrl(selectedProfile)"
              />
            </el-form-item>
            <el-form-item label="API_KEY">
              <el-input
                v-model="selectedProfile.api_key"
                type="password"
                show-password
                placeholder="sk-..."
              />
            </el-form-item>
            <el-form-item label="额外请求体">
              <div class="extra-body-block">
                <el-input
                  v-model="extraBodyText"
                  type="textarea"
                  :rows="5"
                  placeholder='{"response_format":{"type":"json_object"}}'
                  class="extra-body-textarea"
                  @blur="onExtraBodyBlur"
                />
                <el-button size="small" @click="fillDeepseekJsonOutput">填入 DeepSeek JSON 预设</el-button>
              </div>
            </el-form-item>
            <el-form-item label="Model 子池">
              <div class="model-pool">
                <div class="model-tags">
                  <el-tag
                    v-for="model in selectedProfile.models"
                    :key="model"
                    closable
                    :disable-transitions="false"
                    @close="handleRemoveModel(model)"
                  >
                    {{ model }}
                  </el-tag>
                </div>
                <div class="model-add-row">
                  <el-input
                    v-model="newModelInput"
                    placeholder="输入 model_name 后回车添加"
                    @keyup.enter="handleAddModel"
                  />
                  <el-button @click="handleAddModel">添加</el-button>
                </div>
              </div>
            </el-form-item>
            <el-form-item>
              <el-button @click="clearAllProfiles">清除全部配置</el-button>
            </el-form-item>
          </el-form>
        </div>
        <el-empty v-else description="请新增或选择 API 配置" />
      </el-col>
    </el-row>
  </el-card>
</template>

<style scoped>
.page-card {
  border: none;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.storage-hint {
  margin: 0 0 20px;
  font-size: 13px;
  color: #909399;
  line-height: 1.6;
}

.layout-row {
  align-items: stretch;
}

.side-panel {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  min-height: 420px;
}

.side-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  font-weight: 600;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
}

.profile-menu {
  border-right: none;
}

.profile-menu-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.4;
  padding: 4px 0;
}

.profile-name {
  font-size: 14px;
}

.profile-host {
  font-size: 12px;
  color: #909399;
}

.detail-panel {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
  min-height: 420px;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  font-weight: 600;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
}

.config-form {
  padding: 16px 14px;
  max-width: 640px;
}

.model-pool {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.model-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.model-add-row {
  display: flex;
  gap: 8px;
}

.extra-body-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.extra-body-textarea {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}
</style>
