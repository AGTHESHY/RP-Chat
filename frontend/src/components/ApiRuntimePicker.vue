<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { formatApiDisplayUrl } from '../composables/useApiProfileRegistry'
import { usePageRuntime } from '../composables/usePageRuntime'
import type { RuntimeScope } from '../utils/apiProfileStorage'

const props = defineProps<{
  scope: RuntimeScope
}>()

const router = useRouter()
const {
  runtime,
  registry,
  currentProfile,
  availableModels,
  hasValidRuntime,
  switchProfile,
  switchModel,
  syncWithRegistry,
} = usePageRuntime(props.scope)

onMounted(() => {
  syncWithRegistry()
})

const apiDisplayLabel = computed(() => {
  if (!currentProfile.value) return '未配置'
  return currentProfile.value.name
})

const apiDisplayHost = computed(() =>
  currentProfile.value ? formatApiDisplayUrl(currentProfile.value.base_url) : '',
)

const modelDisplay = computed(() => runtime.value.modelName || '未选择')
</script>

<template>
  <div class="api-summary">
    <template v-if="hasValidRuntime && currentProfile">
      <el-dropdown trigger="click" @command="switchProfile">
        <span class="api-meta-chip api-meta-chip--api api-meta-chip--clickable">
          <span class="api-meta-label">API</span>
          <span class="api-meta-value">{{ apiDisplayLabel }}</span>
          <span v-if="apiDisplayHost" class="api-meta-sub">{{ apiDisplayHost }}</span>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="item in registry.profiles"
              :key="item.id"
              :command="item.id"
              :class="{ 'is-active': item.id === runtime.apiProfileId }"
            >
              {{ item.name }} · {{ formatApiDisplayUrl(item.base_url) }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <el-dropdown trigger="click" @command="switchModel">
        <span class="api-meta-chip api-meta-chip--model api-meta-chip--clickable">
          <span class="api-meta-label">模型</span>
          <span class="api-meta-value">{{ modelDisplay }}</span>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="model in availableModels"
              :key="model"
              :command="model"
              :class="{ 'is-active': model === runtime.modelName }"
            >
              {{ model }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </template>
    <el-link
      v-else
      type="primary"
      :underline="false"
      class="api-link"
      @click="router.push('/api-config')"
    >
      未配置 API，前往设置
    </el-link>
  </div>
</template>

<style scoped>
.api-summary {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 6px;
  min-width: 0;
  justify-content: flex-end;
}

.api-meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 240px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
  overflow: hidden;
}

.api-meta-chip--clickable {
  cursor: pointer;
  transition: opacity 0.15s;
}

.api-meta-chip--clickable:hover {
  opacity: 0.85;
}

.api-meta-chip--api {
  background: #f4f4f5;
  color: #606266;
}

.api-meta-chip--model {
  background: #ecf5ff;
  color: #409eff;
}

.api-meta-label {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 400;
  opacity: 0.72;
}

.api-meta-value {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  font-weight: 500;
}

.api-meta-sub {
  flex-shrink: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
  opacity: 0.65;
}

.api-link {
  font-size: 12px;
  white-space: nowrap;
}

:deep(.el-dropdown-menu__item.is-active) {
  color: #409eff;
  font-weight: 500;
}
</style>
