<script setup lang="ts">
import { computed } from 'vue'
import {
  parseRpEvalJson,
  type RpEvalModuleResult,
  type RpEvalParsed,
} from '../utils/parseRpEvalJson'
import { formatConfidence } from '../utils/format'

const props = defineProps<{
  rawContent: string
  parsed?: RpEvalParsed | null
}>()

const parseResult = computed(() => {
  if (props.parsed) {
    return { ok: true as const, data: props.parsed }
  }
  return parseRpEvalJson(props.rawContent)
})

function confidenceTagType(confidence: number): 'success' | 'warning' | 'danger' {
  if (confidence >= 0.8) return 'success'
  if (confidence >= 0.5) return 'warning'
  return 'danger'
}

function moduleTitle(module: RpEvalModuleResult, label: string): string {
  if (!module.available) return `${label}（未参与）`
  return `${label} · ${module.subscore} 分`
}
</script>

<template>
  <div v-if="!parseResult.ok" class="eval-parse-error">
    <el-alert type="error" :title="parseResult.error || '解析失败'" show-icon :closable="false" />
    <el-scrollbar v-if="rawContent" max-height="240px" class="raw-fallback">
      <pre class="raw-pre">{{ rawContent }}</pre>
    </el-scrollbar>
  </div>

  <div v-else-if="parseResult.data" class="eval-result">
    <div class="overall-block">
      <div class="overall-scores">
        <span class="overall-score">{{ parseResult.data.overall_score }}</span>
        <span class="overall-label">综合分</span>
        <el-tag :type="confidenceTagType(parseResult.data.overall_confidence)" size="small">
          置信度 {{ formatConfidence(parseResult.data.overall_confidence) }}
        </el-tag>
      </div>
      <p v-if="parseResult.data.summary" class="summary">{{ parseResult.data.summary }}</p>
    </div>

    <section
      v-if="parseResult.data.segment_compress.available"
      class="module-section"
    >
      <h4 class="module-title">
        {{ moduleTitle(parseResult.data.segment_compress, 'Segment 压缩') }}
        <el-tag
          :type="confidenceTagType(parseResult.data.segment_compress.confidence)"
          size="small"
        >
          模块置信 {{ formatConfidence(parseResult.data.segment_compress.confidence) }}
        </el-tag>
      </h4>
      <div
        v-for="dim in parseResult.data.segment_compress.dimensions"
        :key="dim.id"
        class="dimension-card"
      >
        <div class="dim-header">
          <span class="dim-name">{{ dim.name }}</span>
          <span class="dim-score">{{ dim.score }}</span>
          <el-tag :type="confidenceTagType(dim.confidence)" size="small">
            {{ formatConfidence(dim.confidence) }}
          </el-tag>
        </div>
        <el-progress :percentage="dim.score" :stroke-width="8" :show-text="false" />
        <p v-if="dim.evidence" class="dim-evidence">{{ dim.evidence }}</p>
        <ul v-if="dim.issues.length" class="dim-issues">
          <li v-for="(issue, i) in dim.issues" :key="i">{{ issue }}</li>
        </ul>
      </div>
    </section>

    <section v-if="parseResult.data.history_merge.available" class="module-section">
      <h4 class="module-title">
        {{ moduleTitle(parseResult.data.history_merge, 'History 合并') }}
        <el-tag
          :type="confidenceTagType(parseResult.data.history_merge.confidence)"
          size="small"
        >
          模块置信 {{ formatConfidence(parseResult.data.history_merge.confidence) }}
        </el-tag>
      </h4>
      <div
        v-for="dim in parseResult.data.history_merge.dimensions"
        :key="dim.id"
        class="dimension-card"
      >
        <div class="dim-header">
          <span class="dim-name">{{ dim.name }}</span>
          <span class="dim-score">{{ dim.score }}</span>
          <el-tag :type="confidenceTagType(dim.confidence)" size="small">
            {{ formatConfidence(dim.confidence) }}
          </el-tag>
        </div>
        <el-progress :percentage="dim.score" :stroke-width="8" :show-text="false" />
        <p v-if="dim.evidence" class="dim-evidence">{{ dim.evidence }}</p>
        <ul v-if="dim.issues.length" class="dim-issues">
          <li v-for="(issue, i) in dim.issues" :key="i">{{ issue }}</li>
        </ul>
      </div>
    </section>

    <section
      v-if="parseResult.data.cross_consistency.available"
      class="module-section cross-section"
    >
      <h4 class="module-title">
        交叉一致性 · {{ parseResult.data.cross_consistency.score }} 分
        <el-tag
          :type="confidenceTagType(parseResult.data.cross_consistency.confidence)"
          size="small"
        >
          {{ formatConfidence(parseResult.data.cross_consistency.confidence) }}
        </el-tag>
      </h4>
      <p v-if="parseResult.data.cross_consistency.notes" class="cross-notes">
        {{ parseResult.data.cross_consistency.notes }}
      </p>
    </section>

    <section v-if="parseResult.data.recommendations.length" class="recommendations">
      <h4 class="module-title">改进建议</h4>
      <ul>
        <li v-for="(item, index) in parseResult.data.recommendations" :key="index">{{ item }}</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.eval-result {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.overall-block {
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;
}

.overall-scores {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.overall-score {
  font-size: 32px;
  font-weight: 700;
  color: #303133;
  line-height: 1;
}

.overall-label {
  font-size: 14px;
  color: #606266;
}

.summary {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

.module-section {
  border-top: 1px solid #ebeef5;
  padding-top: 12px;
}

.module-title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.dimension-card {
  margin-bottom: 12px;
  padding: 10px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
}

.dim-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.dim-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.dim-score {
  font-size: 16px;
  font-weight: 600;
}

.dim-evidence {
  margin: 8px 0 0;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}

.dim-issues {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: #f56c6c;
}

.cross-notes {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: #606266;
}

.recommendations ul {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

.raw-fallback {
  margin-top: 12px;
}

.raw-pre {
  margin: 0;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
