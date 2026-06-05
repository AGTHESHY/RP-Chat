<script setup lang="ts">
import StreamingOutput from './StreamingOutput.vue'

defineProps<{
  streaming: boolean
  content: string
  reasoning?: string
}>()
</script>

<template>
  <div class="stream-result-panel">
    <Transition name="stream-handoff" mode="out-in">
      <StreamingOutput
        v-if="streaming"
        key="streaming"
        class="stream-result-panel__body"
        :content="content"
        :reasoning="reasoning"
        :done="false"
      />
      <div v-else key="result" class="stream-result-panel__body stream-result-panel__result">
        <slot />
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.stream-result-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.stream-result-panel__body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.stream-result-panel__result {
  overflow: hidden;
  overflow-y: auto;
}

/* 流式区渐进收缩，结构化结果淡入 */
.stream-handoff-leave-active {
  transition:
    opacity 0.4s ease,
    max-height 0.55s cubic-bezier(0.4, 0, 0.2, 1),
    transform 0.55s cubic-bezier(0.4, 0, 0.2, 1),
    margin 0.55s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  transform-origin: top center;
}

.stream-handoff-leave-from {
  opacity: 1;
  max-height: 70vh;
  transform: scaleY(1);
}

.stream-handoff-leave-to {
  opacity: 0;
  max-height: 0;
  transform: scaleY(0.94);
  margin-top: 0;
  margin-bottom: 0;
}

.stream-handoff-enter-active {
  transition: opacity 0.5s ease 0.12s;
}

.stream-handoff-enter-from {
  opacity: 0;
}

.stream-handoff-enter-to {
  opacity: 1;
}
</style>
