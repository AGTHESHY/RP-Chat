<script setup lang="ts">
withDefaults(
  defineProps<{
    leftSpan?: number
    centerSpan?: number
    rightSpan?: number
  }>(),
  {
    leftSpan: 6,
    centerSpan: 9,
    rightSpan: 9,
  },
)
</script>

<template>
  <el-card class="page-card" shadow="never">
    <el-row :gutter="16" class="full-height">
      <el-col :span="leftSpan" class="full-height">
        <slot name="left" />
      </el-col>
      <el-col :span="centerSpan" class="full-height">
        <slot name="center" />
      </el-col>
      <el-col :span="rightSpan" class="full-height">
        <slot name="right" />
      </el-col>
    </el-row>
  </el-card>
</template>
