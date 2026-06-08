<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ResultTreeNode } from '../utils/resultTree'

const props = withDefaults(
  defineProps<{
    nodes: ResultTreeNode[]
    nested?: boolean
    defaultExpanded?: string[]
  }>(),
  {
    nested: false,
    defaultExpanded: () => [],
  },
)

const expanded = ref<string[]>([...props.defaultExpanded])

watch(
  () => props.defaultExpanded,
  (value) => {
    if (!props.nested) {
      expanded.value = [...value]
    }
  },
)
</script>

<template>
  <el-collapse v-model="expanded" class="result-tree" :class="{ 'result-tree--nested': nested }">
    <el-collapse-item v-for="node in nodes" :key="node.id" :name="node.id">
      <template #title>
        <div class="result-tree-title">
          <span class="result-tree-label">{{ node.label }}</span>
          <span v-if="node.preview && !expanded.includes(node.id)" class="result-tree-preview">
            {{ node.preview }}
          </span>
        </div>
      </template>

      <pre v-if="node.content" class="result-tree-text prompt-pre">{{ node.content }}</pre>

      <ResultTreeView
        v-if="node.children?.length"
        :nodes="node.children"
        nested
      />
    </el-collapse-item>
  </el-collapse>
</template>

<style scoped>
.result-tree {
  border: none;
}

.result-tree--nested {
  margin-top: 4px;
  padding-left: 12px;
  border-left: 2px solid #ebeef5;
}

.result-tree :deep(.el-collapse-item__header) {
  min-height: 34px;
  height: auto;
  line-height: 1.4;
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  border: none;
  background: transparent;
}

.result-tree :deep(.el-collapse-item__wrap) {
  border: none;
}

.result-tree :deep(.el-collapse-item__content) {
  padding-bottom: 8px;
}

.result-tree-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  padding-right: 8px;
}

.result-tree-label {
  flex-shrink: 0;
  font-weight: 600;
}

.result-tree-preview {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  font-weight: 400;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-tree-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
