<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

const props = defineProps<{
  content: string
  reasoning?: string
  done?: boolean
}>()

const reasoningExpanded = ref<string[]>(['reasoning'])
const scrollRef = ref<HTMLElement | null>(null)

async function scrollToBottom() {
  await nextTick()
  const el = scrollRef.value
  if (el) {
    el.scrollTop = el.scrollHeight
  }
}

watch(
  () => [props.content, props.reasoning],
  () => {
    void scrollToBottom()
  },
)
</script>

<template>
  <div class="streaming-output">
    <div v-if="!done" class="streaming-status">
      <span class="streaming-dot" />
      <span>生成中…</span>
    </div>

    <el-collapse v-if="reasoning" v-model="reasoningExpanded" class="streaming-reasoning">
      <el-collapse-item name="reasoning">
        <template #title>
          <span class="reasoning-title">推理过程</span>
        </template>
        <pre class="reasoning-pre">{{ reasoning }}</pre>
      </el-collapse-item>
    </el-collapse>

    <div ref="scrollRef" class="streaming-body">
      <pre class="streaming-pre">{{ content }}<span v-if="!done" class="streaming-caret">▋</span></pre>
    </div>
  </div>
</template>

<style scoped>
.streaming-output {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 0;
}

.streaming-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
}

.streaming-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #409eff;
  animation: streaming-pulse 1s ease-in-out infinite;
}

@keyframes streaming-pulse {
  0%,
  100% {
    opacity: 0.3;
  }
  50% {
    opacity: 1;
  }
}

.streaming-reasoning {
  flex-shrink: 0;
  border-radius: 6px;
  background: #f7f8fa;
  padding: 0 10px;
}

.reasoning-title {
  font-size: 12px;
  color: #909399;
}

.reasoning-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.6;
  color: #909399;
}

.streaming-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  border-radius: 6px;
  background: #fafafa;
  padding: 10px 12px;
}

.streaming-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.65;
  color: #303133;
}

.streaming-caret {
  color: #409eff;
  animation: streaming-blink 1s step-end infinite;
}

@keyframes streaming-blink {
  50% {
    opacity: 0;
  }
}
</style>
