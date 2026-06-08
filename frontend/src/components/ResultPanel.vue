<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PromptType } from '../api'
import ResultTreeView from './ResultTreeView.vue'
import { buildResultTree } from '../utils/resultTree'

const props = defineProps<{
  content: string
  promptType: PromptType
}>()

interface FieldCheck {
  label: string
  ok: boolean
}

interface ParseResult {
  ok: boolean
  error?: string
  parsed?: Record<string, unknown>
  checks: FieldCheck[]
  segmentLength?: number
  memoryStateLength?: number
  historyMemoryLength?: number
}

function stripMarkdownFence(text: string): string {
  let clean = text.trim()
  if (clean.startsWith('```')) {
    const firstNewline = clean.indexOf('\n')
    if (firstNewline !== -1) {
      clean = clean.slice(firstNewline + 1)
    }
    if (clean.endsWith('```')) {
      clean = clean.slice(0, -3)
    }
  }
  return clean.trim()
}

const result = computed<ParseResult>(() => {
  if (!props.content) {
    return { ok: false, checks: [] }
  }

  try {
    const parsed = JSON.parse(stripMarkdownFence(props.content)) as Record<string, unknown>
    const checks: FieldCheck[] = []

    if (props.promptType === 'segment_compress') {
      const topFields = ['history_segment', 'memory_state']
      for (const field of topFields) {
        checks.push({ label: field, ok: field in parsed })
      }

      const msFields = [
        'scene_state',
        'open_loops',
        'user_profile',
        'relationship',
        'character_state',
        'group_context',
      ]
      const ms = parsed.memory_state as Record<string, unknown> | undefined
      if (ms) {
        for (const field of msFields) {
          checks.push({ label: `memory_state.${field}`, ok: field in ms })
        }
      }

      const seg = String(parsed.history_segment ?? '')
      const msStr = JSON.stringify(parsed.memory_state ?? {})
      return {
        ok: checks.every((c) => c.ok),
        parsed,
        checks,
        segmentLength: seg.length,
        memoryStateLength: msStr.length,
      }
    }

    checks.push({ label: 'history_memory', ok: 'history_memory' in parsed })
    const hm = String(parsed.history_memory ?? '')
    return {
      ok: checks.every((c) => c.ok),
      parsed,
      checks,
      historyMemoryLength: hm.length,
    }
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'JSON 解析失败',
      checks: [],
    }
  }
})

const formattedJson = computed(() => {
  if (!result.value.parsed) return ''
  return JSON.stringify(result.value.parsed, null, 2)
})

const viewMode = ref<'tree' | 'raw'>('tree')

const resultTree = computed(() => {
  if (!result.value.parsed) return []
  return buildResultTree(result.value.parsed, props.promptType)
})

const validationExpanded = ref<string[]>([])

const validationTitle = computed(() => {
  const checks = result.value.checks
  if (result.value.error) return 'JSON 解析验证 · 解析失败'
  if (!checks.length) return 'JSON 解析验证'
  const passed = checks.filter((item) => item.ok).length
  return `JSON 解析验证 · ${passed}/${checks.length} 通过`
})

</script>

<template>
  <div class="result-panel">
    <div class="section json-output-section">
      <div class="json-output-header">
        <h4>结果预览</h4>
        <el-radio-group v-if="formattedJson" v-model="viewMode" size="small" class="view-mode-switch">
          <el-radio-button value="tree">树形</el-radio-button>
          <el-radio-button value="raw">原始 JSON</el-radio-button>
        </el-radio-group>
      </div>
      <div class="json-scroll-host">
        <el-scrollbar v-if="formattedJson && viewMode === 'tree'">
          <ResultTreeView :nodes="resultTree" />
        </el-scrollbar>
        <el-scrollbar v-else-if="formattedJson && viewMode === 'raw'">
          <pre class="prompt-pre">{{ formattedJson }}</pre>
        </el-scrollbar>
        <p v-else class="json-empty">暂无可用 JSON（可展开下方解析验证查看说明）</p>
      </div>
    </div>

    <el-collapse
      v-if="content"
      v-model="validationExpanded"
      class="validation-collapse validation-footer"
    >
      <el-collapse-item name="validation" :title="validationTitle">
        <p v-if="result.error" class="error">解析失败: {{ result.error }}</p>
        <ul v-if="result.checks.length" class="checks">
          <li v-for="item in result.checks" :key="item.label">
            <span :class="item.ok ? 'ok' : 'fail'">{{ item.ok ? '✅' : '❌' }}</span>
            {{ item.label }}
          </li>
        </ul>
        <div v-if="result.segmentLength !== undefined" class="meta">
          history_segment 长度: {{ result.segmentLength }} chars
        </div>
        <div v-if="result.memoryStateLength !== undefined" class="meta">
          memory_state 长度: {{ result.memoryStateLength }} chars
        </div>
        <div v-if="result.historyMemoryLength !== undefined" class="meta">
          history_memory 长度: {{ result.historyMemoryLength }} chars
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.result-panel {
  display: flex;
  flex-direction: column;
  min-height: 280px;
  height: 100%;
  gap: 0;
}

.json-output-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.json-output-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.json-output-header h4 {
  margin: 0;
  font-size: 14px;
}

.view-mode-switch {
  flex-shrink: 0;
}

.json-scroll-host {
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
}

.json-scroll-host :deep(.el-scrollbar) {
  height: 100%;
}

.json-scroll-host :deep(.el-scrollbar__wrap) {
  overflow-x: hidden;
}

.checks {
  list-style: none;
  padding: 0;
  margin: 0;
}

.checks li {
  font-size: 13px;
  line-height: 1.8;
}

.ok {
  color: #67c23a;
}

.fail {
  color: #f56c6c;
}

.error {
  color: #f56c6c;
  font-size: 13px;
}

.meta {
  font-size: 13px;
  color: #606266;
  margin-top: 4px;
}

.json-empty {
  margin: 0;
  font-size: 13px;
  color: #909399;
}

.validation-footer {
  flex-shrink: 0;
  margin-top: 8px;
  padding-top: 4px;
  border-top: 1px solid #ebeef5;
}

.validation-collapse {
  border: none;
}

.validation-collapse :deep(.el-collapse-item__header) {
  height: 36px;
  line-height: 36px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  border: none;
  background: transparent;
}

.validation-collapse :deep(.el-collapse-item__wrap) {
  border: none;
}

.validation-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 4px;
}
</style>
