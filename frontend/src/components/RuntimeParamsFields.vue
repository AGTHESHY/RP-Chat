<script setup lang="ts">
defineProps<{
  temperature: number
  topK: number | null
  labelWidth?: string
}>()

const emit = defineEmits<{
  'update:temperature': [value: number]
  'update:topK': [value: number | null]
}>()
</script>

<template>
  <el-form-item label="temperature" :label-width="labelWidth">
    <el-input-number
      :model-value="temperature"
      :min="0"
      :max="2"
      :step="0.1"
      @update:model-value="emit('update:temperature', $event as number)"
    />
  </el-form-item>
  <el-form-item label="top_k" :label-width="labelWidth">
    <el-input-number
      :model-value="topK ?? undefined"
      :min="1"
      :max="100"
      :step="1"
      @update:model-value="emit('update:topK', ($event as number) ?? null)"
    />
  </el-form-item>
</template>
