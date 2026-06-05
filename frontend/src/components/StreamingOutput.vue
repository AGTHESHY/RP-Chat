<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

const props = defineProps<{
  content: string
  reasoning?: string
  done?: boolean
}>()

const reasoningExpanded = ref<string[]>(['reasoning'])
const scrollRef = ref<HTMLElement | null>(null)
const reasoningScrollRef = ref<HTMLElement | null>(null)

async function scrollToBottom() {
  await nextTick()
  for (const el of [scrollRef.value, reasoningScrollRef.value]) {
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  }
}

watch(
  () => props.content,
  () => {
    void scrollToBottom()
  },
)

watch(
  () => props.reasoning,
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
        <div ref="reasoningScrollRef" class="reasoning-scroll">
          <pre class="reasoning-pre">{{ reasoning }}</pre>
        </div>
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
  flex: 0 1 auto;
  min-height: 0;
  max-height: min(42vh, 300px);
  border-radius: 6px;
  background: #f7f8fa;
  padding: 0 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.streaming-reasoning :deep(.el-collapse-item__wrap) {
  overflow: hidden;
}

.streaming-reasoning :deep(.el-collapse-item__content) {
  padding: 0 0 6px;
}

.reasoning-scroll {
  max-height: min(36vh, 260px);
  overflow-x: hidden;
  overflow-y: auto;
  box-sizing: border-box;
  /* 右侧留空给滚动条，底部留空防末行被裁切 */
  padding: 2px 16px 12px 2px;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: rgba(144, 147, 153, 0.55) transparent;
}

.reasoning-scroll::-webkit-scrollbar {
  width: 8px;
}

.reasoning-scroll::-webkit-scrollbar-track {
  background: transparent;
  margin: 2px 0;
}

.reasoning-scroll::-webkit-scrollbar-thumb {
  border-radius: 4px;
  background: rgba(144, 147, 153, 0.45);
  border: 2px solid transparent;
  background-clip: padding-box;
}

.reasoning-title {
  font-size: 12px;
  color: #909399;
}

.reasoning-pre {
  margin: 0;
  padding: 0;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  font-size: 12px;
  line-height: 1.6;
  color: #909399;
}

.streaming-body {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  box-sizing: border-box;
  border-radius: 6px;
  background: #fafafa;
  padding: 10px 16px 14px 12px;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: rgba(144, 147, 153, 0.55) transparent;
}

.streaming-body::-webkit-scrollbar {
  width: 8px;
}

.streaming-body::-webkit-scrollbar-track {
  background: transparent;
  margin: 2px 0;
}

.streaming-body::-webkit-scrollbar-thumb {
  border-radius: 4px;
  background: rgba(144, 147, 153, 0.45);
  border: 2px solid transparent;
  background-clip: padding-box;
}

.streaming-pre {
  margin: 0;
  padding: 0;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
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
