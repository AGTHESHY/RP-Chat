<script setup lang="ts">
import JsonVisualValue from './JsonVisualValue.vue'

defineProps<{
  data: unknown
}>()
</script>

<template>
  <div class="json-visual-viewer">
    <JsonVisualValue :value="data" :depth="0" />
  </div>
</template>

<style scoped>
.json-visual-viewer {
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.65;
  word-break: break-word;
}
</style>
