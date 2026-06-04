<script setup lang="ts">
import { computed } from 'vue'

export interface AdaptiveTabItem {
  label: string
  name: string
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    modelValue: string
    items: AdaptiveTabItem[]
    /** stretch：均分容器宽度；scroll：超出横向滚动 */
    layout?: 'stretch' | 'scroll'
  }>(),
  {
    layout: 'stretch',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  tabClick: [value: string]
}>()

const active = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
})

function onTabClick(pane: { paneName?: string | number }) {
  if (pane.paneName !== undefined && pane.paneName !== null) {
    emit('tabClick', String(pane.paneName))
  }
}
</script>

<template>
  <el-tabs
    v-model="active"
    class="adaptive-tabs"
    :class="[`adaptive-tabs--${layout}`]"
    @tab-click="onTabClick"
  >
    <el-tab-pane
      v-for="item in items"
      :key="item.name"
      :label="item.label"
      :name="item.name"
      :disabled="item.disabled"
    />
  </el-tabs>
</template>

<style scoped>
.adaptive-tabs {
  width: 100%;
  min-width: 0;
  flex-shrink: 0;
  padding: 0 8px;
}

.adaptive-tabs :deep(.el-tabs__header) {
  margin: 0;
  width: 100%;
}

.adaptive-tabs :deep(.el-tabs__nav-wrap) {
  width: 100%;
  margin-bottom: 0;
}

.adaptive-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background-color: #e4e7ed;
}

.adaptive-tabs :deep(.el-tabs__nav-scroll) {
  width: 100%;
}

.adaptive-tabs :deep(.el-tabs__content) {
  display: none;
}

.adaptive-tabs--stretch :deep(.el-tabs__nav) {
  display: flex;
  width: 100%;
  float: none;
}

.adaptive-tabs--stretch :deep(.el-tabs__item) {
  flex: 1;
  min-width: 0;
  padding: 0 10px;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.adaptive-tabs--scroll :deep(.el-tabs__nav) {
  display: inline-flex;
  min-width: 100%;
}

.adaptive-tabs--scroll :deep(.el-tabs__nav-scroll) {
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
}

.adaptive-tabs--scroll :deep(.el-tabs__item) {
  flex-shrink: 0;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
