<script setup lang="ts">
defineProps<{
  content: string
}>()

const expanded = defineModel<string[]>('expanded', { default: () => [] })
</script>

<template>
  <el-collapse v-if="content" v-model="expanded" class="reasoning-collapse">
    <el-collapse-item title="推理内容 (reasoning_content)" name="reasoning">
      <pre class="prompt-pre">{{ content }}</pre>
    </el-collapse-item>
  </el-collapse>
</template>
