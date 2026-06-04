<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  modelValue: string
  filename?: string
  saving?: boolean
  readonly?: boolean
  showSave?: boolean
  saveLabel?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  save: []
}>()

const showSaveButton = computed(() => props.showSave !== false && !props.readonly)

async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.modelValue)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}
</script>

<template>
  <div class="prompt-viewer">
    <div class="toolbar">
      <span class="filename">{{ filename || '未选择文件' }}</span>
      <div class="actions">
        <el-button size="small" :disabled="!modelValue" @click="copyContent">复制</el-button>
        <el-button
          v-if="showSaveButton"
          size="small"
          type="primary"
          :loading="saving"
          :disabled="!filename"
          @click="emit('save')"
        >
          {{ saveLabel || '保存到 MySQL' }}
        </el-button>
      </div>
    </div>
    <el-input
      :model-value="modelValue"
      type="textarea"
      class="editor"
      :readonly="readonly"
      :placeholder="filename ? '编辑 System Prompt 正文' : '请从左侧选择提示词文件'"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>
</template>

<style scoped>
.prompt-viewer {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
}

.filename {
  font-size: 13px;
  color: #606266;
  font-weight: 500;
}

.actions {
  display: flex;
  gap: 8px;
}

.editor {
  flex: 1;
  width: 100%;
  min-height: 0;
}

.editor :deep(.el-textarea) {
  width: 100%;
}

.editor :deep(.el-textarea__inner) {
  width: 100%;
  height: 100%;
  min-height: 420px;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
  border: none;
  border-radius: 0;
  box-shadow: none;
  resize: none;
}
</style>
