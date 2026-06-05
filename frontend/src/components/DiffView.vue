<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  computeLineDiff,
  hasDiffChanges,
  toNewSideSegments,
  toOldSideSegments,
  type CharDiffType,
  type DiffLineType,
} from '../utils/textDiff'

const props = defineProps<{
  oldText: string
  newText: string
  filename?: string
  side: 'old' | 'new'
  readonly?: boolean
}>()

const diffLines = computed(() => computeLineDiff(props.oldText, props.newText))
const hasChanges = computed(() => hasDiffChanges(diffLines.value))

const segments = computed(() =>
  props.side === 'old'
    ? toOldSideSegments(diffLines.value)
    : toNewSideSegments(diffLines.value),
)

function lineClass(type: DiffLineType): string {
  if (type === 'unchanged') return 'diff-line--unchanged'
  if (type === 'modified') return 'diff-line--modified'
  if (type === 'added') return 'diff-line--added'
  return 'diff-line--removed'
}

function charClass(type: CharDiffType): string {
  if (type === 'unchanged') return 'diff-char--unchanged'
  if (type === 'modified') return 'diff-char--modified'
  if (type === 'added') return 'diff-char--added'
  return 'diff-char--removed'
}

async function copyContent() {
  const text = props.side === 'old' ? props.oldText : props.newText
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}
</script>

<template>
  <div class="diff-view">
    <div class="toolbar">
      <span class="filename">{{ filename || '对比视图' }}</span>
      <div class="actions">
        <span v-if="hasChanges" class="diff-legend">
          <span class="legend-item legend-modified">修改</span>
          <span v-if="side === 'new'" class="legend-item legend-added">新增</span>
          <span v-if="side === 'old'" class="legend-item legend-removed">删除</span>
        </span>
        <span v-else class="diff-no-change">与基线无差异</span>
        <el-button size="small" :disabled="!oldText && !newText" @click="copyContent">
          复制
        </el-button>
      </div>
    </div>
    <el-scrollbar class="diff-scroll">
      <pre v-if="segments.length" class="diff-content"><span
        v-for="(seg, idx) in segments"
        :key="idx"
        :class="['diff-line', lineClass(seg.type)]"
      ><template v-if="seg.chars?.length"><span
          v-for="(ch, cidx) in seg.chars"
          :key="cidx"
          :class="['diff-char', charClass(ch.type)]"
        >{{ ch.text }}</span></template><template v-else>{{ seg.text }}</template>{{ idx < segments.length - 1 ? '\n' : '' }}</span></pre>
      <p v-else class="diff-empty">暂无内容</p>
    </el-scrollbar>
  </div>
</template>

<style scoped>
.diff-view {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
}

.filename {
  font-size: 13px;
  color: #606266;
  font-weight: 500;
  flex-shrink: 0;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.diff-legend {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}

.diff-no-change {
  font-size: 12px;
  color: #909399;
}

.legend-item {
  padding: 1px 6px;
  border-radius: 3px;
}

.legend-modified {
  color: #b88230;
  background: #fdf6ec;
}

.legend-added {
  color: #529b2e;
  background: #f0f9eb;
}

.legend-removed {
  color: #c45656;
  background: #fef0f0;
}

.diff-scroll {
  flex: 1;
  min-height: 0;
}

.diff-content {
  margin: 0;
  padding: 14px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
}

.diff-line {
  display: inline;
}

.diff-line--unchanged {
  color: #303133;
}

.diff-line--modified {
  color: #303133;
}

.diff-line--added {
  color: #67c23a;
  background: #f0f9eb;
}

.diff-line--removed {
  color: #f56c6c;
  background: #fef0f0;
  text-decoration: line-through;
}

.diff-char--unchanged {
  color: inherit;
}

.diff-char--modified {
  color: #e6a23c;
  background: #fdf6ec;
  font-weight: 600;
}

.diff-char--added {
  color: #67c23a;
  background: #f0f9eb;
  font-weight: 600;
}

.diff-char--removed {
  color: #f56c6c;
  background: #fef0f0;
  text-decoration: line-through;
  font-weight: 600;
}

.diff-empty {
  margin: 0;
  padding: 14px;
  font-size: 13px;
  color: #c0c4cc;
}
</style>
