<script setup lang="ts">
defineProps<{
  title?: string
  titleClass?: string
}>()
</script>

<template>
  <div class="panel">
    <div class="panel-title" :class="titleClass">
      <slot name="title">
        <span v-if="title">{{ title }}</span>
      </slot>
      <div v-if="$slots.actions" class="panel-actions">
        <slot name="actions" />
      </div>
    </div>
    <slot />
  </div>
</template>
