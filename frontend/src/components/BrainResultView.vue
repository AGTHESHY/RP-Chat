<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createVersion, listVersions } from '../api'
import {
  brainRecommendationLabel,
  isValidSuggestedVersionName,
  type BrainParsed,
  type BrainRecommendation,
} from '../utils/parseBrainJson'

const props = defineProps<{
  parsed: BrainParsed
}>()

const router = useRouter()
const creatingVersion = ref<string | null>(null)

const overallTagType = computed(() => {
  const map: Record<BrainRecommendation, 'success' | 'warning' | 'danger'> = {
    hold: 'success',
    minor: 'warning',
    major: 'danger',
  }
  return map[props.parsed.overall]
})

function moduleLabel(promptType: string): string {
  return promptType === 'segment_compress' ? 'Segment 压缩' : 'History 合并'
}

function moduleTagType(rec: BrainRecommendation): 'success' | 'warning' | 'danger' {
  if (rec === 'minor') return 'warning'
  if (rec === 'major') return 'danger'
  return 'success'
}

function goPromptManager(version?: string) {
  if (version) {
    void router.push({ path: '/', query: { version } })
  } else {
    void router.push('/')
  }
}

async function handleCreateVersion(
  name: string,
  baseVersion: string,
  evaluatedVersion: string,
) {
  if (!isValidSuggestedVersionName(name)) {
    ElMessage.warning('建议版本名不合法')
    return
  }
  creatingVersion.value = name
  try {
    const catalog = await listVersions()
    const exists =
      catalog.baselines.includes(name) ||
      catalog.custom.some((v) => v.version === name) ||
      catalog.drafts.some((v) => v.version === name)
    if (exists) {
      ElMessage.warning(`版本 ${name} 已存在`)
      goPromptManager(name)
      return
    }
    await createVersion(name, evaluatedVersion || baseVersion || null)
    ElMessage.success(`已创建草稿版本 ${name}`)
    goPromptManager(name)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '创建版本失败')
  } finally {
    creatingVersion.value = null
  }
}
</script>

<template>
  <div class="brain-result">
    <div class="brain-overall">
      <el-tag :type="overallTagType" size="small">
        {{ brainRecommendationLabel(parsed.overall) }}
      </el-tag>
      <p class="brain-rationale">{{ parsed.overall_rationale || '（无总判说明）' }}</p>
    </div>

    <div v-for="mod in parsed.modules" :key="mod.prompt_type" class="brain-module-card">
      <div class="brain-module-head">
        <span class="brain-module-title">{{ moduleLabel(mod.prompt_type) }}</span>
        <el-tag :type="moduleTagType(mod.recommendation)" size="small">
          {{ brainRecommendationLabel(mod.recommendation) }}
        </el-tag>
        <span class="brain-version-chip">被测 {{ mod.evaluated_version }}</span>
        <span v-if="mod.base_version" class="brain-version-chip">基线 {{ mod.base_version }}</span>
      </div>
      <p class="brain-rationale">{{ mod.rationale }}</p>
      <ul v-if="mod.focus_areas.length" class="brain-focus-list">
        <li v-for="(area, idx) in mod.focus_areas" :key="idx">{{ area }}</li>
      </ul>
      <div v-if="mod.recommendation === 'minor' && mod.suggested_version_name" class="brain-actions">
        <span class="brain-suggest-name">建议 fork：{{ mod.suggested_version_name }}</span>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="creatingVersion === mod.suggested_version_name"
          @click="
            handleCreateVersion(
              mod.suggested_version_name!,
              mod.base_version,
              mod.evaluated_version,
            )
          "
        >
          创建建议版本
        </el-button>
      </div>
      <div v-if="mod.recommendation === 'major' && mod.target_base_version" class="brain-actions">
        <span class="brain-suggest-name">建议切换基线 → {{ mod.target_base_version }}</span>
        <el-button size="small" @click="goPromptManager(mod.target_base_version)">
          查看基线 {{ mod.target_base_version }}
        </el-button>
      </div>
      <div class="brain-actions">
        <el-button size="small" link type="primary" @click="goPromptManager(mod.evaluated_version)">
          打开被测版本 {{ mod.evaluated_version }}
        </el-button>
      </div>
    </div>

    <div v-if="parsed.next_steps.length" class="brain-next-steps">
      <div class="brain-section-label">后续步骤</div>
      <ul class="brain-focus-list">
        <li v-for="(step, idx) in parsed.next_steps" :key="idx">{{ step }}</li>
      </ul>
    </div>

    <div class="brain-footer-actions">
      <el-button size="small" @click="goPromptManager()">前往提示词管理</el-button>
    </div>
  </div>
</template>

<style scoped>
.brain-result {
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 13px;
  line-height: 1.5;
}

.brain-overall {
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.brain-rationale {
  margin: 8px 0 0;
  color: #606266;
}

.brain-module-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fafafa;
}

.brain-module-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
}

.brain-module-title {
  font-weight: 600;
}

.brain-version-chip {
  font-size: 12px;
  color: #909399;
}

.brain-focus-list {
  margin: 6px 0 0;
  padding-left: 18px;
  color: #606266;
}

.brain-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.brain-suggest-name {
  font-size: 12px;
  color: #409eff;
}

.brain-next-steps {
  padding-top: 4px;
}

.brain-section-label {
  font-weight: 600;
  margin-bottom: 4px;
}

.brain-footer-actions {
  padding-top: 4px;
  border-top: 1px solid #ebeef5;
}
</style>
