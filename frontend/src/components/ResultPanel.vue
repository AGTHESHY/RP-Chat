<script setup lang="ts">
import { computed } from 'vue'
import type { PromptType } from '../api'

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
</script>

<template>
  <div class="result-panel">
    <div class="section json-output-section">
      <h4>格式化 JSON</h4>
      <el-scrollbar v-if="formattedJson" max-height="240px">
        <pre class="prompt-pre">{{ formattedJson }}</pre>
      </el-scrollbar>
      <p v-else class="json-empty">暂无可用 JSON（见下方解析说明）</p>
    </div>

    <div class="section">
      <h4>JSON 解析验证</h4>
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
    </div>
  </div>
</template>

<style scoped>
.result-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section h4 {
  margin: 0 0 8px;
  font-size: 14px;
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
</style>
