<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { applyBrainRevision, createVersion, listVersions } from '../api'
import type { ResolvedRuntimeRequest } from '../utils/apiProfileStorage'
import { resolveRevisionPlan, revisionActionLabel } from '../utils/brainRevisionDisplay'
import {
  brainRecommendationLabel,
  devPotentialLabel,
  isValidSuggestedVersionName,
  needsAiAutoRevision,
  type BrainModuleAdvice,
  type BrainParsed,
  type BrainRecommendation,
} from '../utils/parseBrainJson'

const props = defineProps<{
  parsed: BrainParsed
  apiConfig?: ResolvedRuntimeRequest | null
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

function linkedIssuesFor(mod: BrainModuleAdvice): string[] {
  return (
    props.parsed.sp_improvements.find((item) => item.prompt_type === mod.prompt_type)
      ?.linked_issues ?? []
  )
}

function revisionPlanFor(mod: BrainModuleAdvice) {
  return resolveRevisionPlan(mod, linkedIssuesFor(mod))
}

function showRevisionPlan(mod: BrainModuleAdvice): boolean {
  return mod.recommendation === 'minor' && needsAiAutoRevision(mod)
}

function goPromptManager(version?: string) {
  if (version) {
    void router.push({ path: '/', query: { version } })
  } else {
    void router.push('/')
  }
}

async function handleCreateVersion(mod: BrainModuleAdvice) {
  const name = mod.suggested_version_name
  if (!name || !isValidSuggestedVersionName(name)) {
    ElMessage.warning('建议版本名不合法')
    return
  }

  creatingVersion.value = name
  const aiRevision = needsAiAutoRevision(mod)

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

    await createVersion(name, mod.evaluated_version || mod.base_version || null)

    if (aiRevision) {
      const cfg = props.apiConfig
      if (!cfg?.base_url?.trim() || !cfg.api_key?.trim() || !cfg.model?.trim()) {
        ElMessage.warning(`已创建草稿 ${name}，但未配置 API，无法自动 AI 修订`)
        goPromptManager(name)
        return
      }

      const plan = revisionPlanFor(mod)
      await applyBrainRevision(name, {
        prompt_type: mod.prompt_type,
        focus_areas: mod.focus_areas,
        linked_issues: linkedIssuesFor(mod),
        rationale: mod.rationale,
        revision_plan: plan,
        base_url: cfg.base_url,
        api_key: cfg.api_key,
        model: cfg.model,
        temperature: cfg.temperature,
      })
      ElMessage.success(`已创建 ${name}，并由 AI 修订 ZH/EN 草稿`)
    } else {
      ElMessage.success(`已创建参考版本 ${name}（未自动修订）`)
    }

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

    <div v-if="parsed.sp_improvements.length" class="brain-section-card">
      <div class="brain-section-label">SP 可改进点</div>
      <div
        v-for="item in parsed.sp_improvements"
        :key="item.prompt_type"
        class="brain-subsection"
      >
        <div class="brain-module-title">{{ moduleLabel(item.prompt_type) }}</div>
        <ul v-if="item.focus_areas.length" class="brain-focus-list">
          <li v-for="(area, idx) in item.focus_areas" :key="`a-${idx}`">{{ area }}</li>
        </ul>
        <ul v-if="item.linked_issues.length" class="brain-issue-list">
          <li v-for="(issue, idx) in item.linked_issues" :key="`i-${idx}`">{{ issue }}</li>
        </ul>
      </div>
    </div>

    <div
      v-if="parsed.rp_model_insights.available"
      class="brain-section-card"
    >
      <div class="brain-section-label">RP 模型开发潜力</div>
      <p v-if="parsed.rp_model_insights.highest_dev_potential" class="brain-highlight">
        潜力最高：{{ parsed.rp_model_insights.highest_dev_potential }}
      </p>
      <p v-if="parsed.rp_model_insights.ranking.length" class="brain-ranking">
        推荐关注：{{ parsed.rp_model_insights.ranking.join(' › ') }}
      </p>
      <p v-if="parsed.rp_model_insights.notes" class="brain-rationale">
        {{ parsed.rp_model_insights.notes }}
      </p>
      <el-table
        v-if="parsed.rp_model_insights.per_model.length"
        :data="parsed.rp_model_insights.per_model"
        size="small"
        class="brain-model-table"
        stripe
      >
        <el-table-column prop="model" label="模型" min-width="88" show-overflow-tooltip />
        <el-table-column label="分" width="40" align="center" prop="overall_score" />
        <el-table-column label="潜力" width="48" align="center">
          <template #default="{ row }">
            {{ devPotentialLabel(row.dev_potential) }}
          </template>
        </el-table-column>
        <el-table-column prop="summary" label="简评" min-width="100" show-overflow-tooltip />
      </el-table>
      <div
        v-for="m in parsed.rp_model_insights.per_model.filter((x) => x.sp_actionable_issues.length)"
        :key="m.model"
        class="brain-subsection"
      >
        <div class="brain-version-chip">{{ m.model }} · SP 可修复问题</div>
        <ul class="brain-issue-list">
          <li v-for="(issue, idx) in m.sp_actionable_issues" :key="idx">{{ issue }}</li>
        </ul>
      </div>
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

      <div v-if="showRevisionPlan(mod)" class="brain-revision-plan">
        <div class="brain-revision-plan-title">
          AI 修订计划
          <span class="brain-revision-plan-hint">
            （创建时将自动写入 SFW / NSFW 中英文草稿）
          </span>
        </div>

        <div class="brain-revision-column">
          <div class="brain-revision-column-head">SFW 将修改</div>
          <div
            v-for="(item, idx) in revisionPlanFor(mod).sfw"
            :key="`sfw-${idx}`"
            class="brain-revision-item"
          >
            <div class="brain-revision-item-head">
              <el-tag size="small" type="info">{{ revisionActionLabel(item.action) }}</el-tag>
              <span class="brain-revision-section">{{ item.section }}</span>
            </div>
            <div class="brain-revision-summary">{{ item.summary }}</div>
            <div class="brain-revision-detail">{{ item.detail }}</div>
          </div>
          <p v-if="!revisionPlanFor(mod).sfw.length" class="brain-revision-empty">（暂无 SFW 修订项）</p>
        </div>

        <div class="brain-revision-column">
          <div class="brain-revision-column-head">NSFW 将修改</div>
          <div
            v-for="(item, idx) in revisionPlanFor(mod).nsfw"
            :key="`nsfw-${idx}`"
            class="brain-revision-item"
          >
            <div class="brain-revision-item-head">
              <el-tag size="small" type="warning">{{ revisionActionLabel(item.action) }}</el-tag>
              <span class="brain-revision-section">{{ item.section }}</span>
            </div>
            <div class="brain-revision-summary">{{ item.summary }}</div>
            <div class="brain-revision-detail">{{ item.detail }}</div>
          </div>
          <p v-if="!revisionPlanFor(mod).nsfw.length" class="brain-revision-empty">（暂无 NSFW 修订项）</p>
        </div>
      </div>

      <div v-if="mod.recommendation === 'minor' && mod.suggested_version_name" class="brain-actions">
        <span class="brain-suggest-name">建议 fork：{{ mod.suggested_version_name }}</span>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="creatingVersion === mod.suggested_version_name"
          @click="handleCreateVersion(mod)"
        >
          {{ needsAiAutoRevision(mod) ? '创建并 AI 修订' : '创建建议版本' }}
        </el-button>
      </div>
      <div v-if="mod.recommendation === 'major' && mod.target_base_version" class="brain-actions">
        <span class="brain-suggest-name">建议切换基线 → {{ mod.target_base_version }}</span>
        <el-button size="small" @click="goPromptManager(mod.target_base_version)">
          查看基线 {{ mod.target_base_version }}
        </el-button>
      </div>
      <div v-if="mod.recommendation === 'hold' && mod.focus_areas.length > 0 && mod.suggested_version_name" class="brain-actions">
        <span class="brain-suggest-name">可选 fork：{{ mod.suggested_version_name }}</span>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="creatingVersion === mod.suggested_version_name"
          @click="handleCreateVersion(mod)"
        >
          创建参考版本（不自动修订）
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

.brain-revision-plan {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.brain-revision-plan-title {
  font-weight: 600;
  color: #303133;
}

.brain-revision-plan-hint {
  font-weight: 400;
  font-size: 12px;
  color: #909399;
}

.brain-revision-column {
  border-top: 1px dashed #ebeef5;
  padding-top: 8px;
}

.brain-revision-column-head {
  font-size: 12px;
  font-weight: 600;
  color: #409eff;
  margin-bottom: 6px;
}

.brain-revision-item {
  padding: 8px 0;
  border-bottom: 1px solid #f0f2f5;
}

.brain-revision-item:last-child {
  border-bottom: none;
}

.brain-revision-item-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 4px;
}

.brain-revision-section {
  font-weight: 500;
  color: #303133;
}

.brain-revision-summary {
  font-size: 12px;
  color: #606266;
}

.brain-revision-detail {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
  line-height: 1.55;
}

.brain-revision-empty {
  margin: 0;
  font-size: 12px;
  color: #c0c4cc;
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

.brain-section-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fff;
}

.brain-subsection {
  margin-top: 8px;
}

.brain-subsection:first-of-type {
  margin-top: 4px;
}

.brain-highlight {
  margin: 6px 0 0;
  font-weight: 500;
  color: #303133;
}

.brain-ranking {
  margin: 4px 0 0;
  font-size: 12px;
  color: #606266;
}

.brain-issue-list {
  margin: 4px 0 0;
  padding-left: 18px;
  color: #e6a23c;
  font-size: 12px;
}

.brain-model-table {
  margin-top: 8px;
  width: 100%;
}

.brain-footer-actions {
  padding-top: 4px;
  border-top: 1px solid #ebeef5;
}
</style>
