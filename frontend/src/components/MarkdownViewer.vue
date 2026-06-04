<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps<{
  content: string
}>()

const html = computed(() => marked.parse(props.content || '') as string)
</script>

<template>
  <div class="markdown-body" v-html="html" />
</template>
