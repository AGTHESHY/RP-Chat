<script setup lang="ts">
defineProps<{
  showQuery?: boolean
}>()

const emit = defineEmits<{
  query: []
}>()
</script>

<template>
  <div class="filters">
    <slot />
    <el-button v-if="showQuery !== false" size="small" @click="emit('query')">查询</el-button>
  </div>
</template>
