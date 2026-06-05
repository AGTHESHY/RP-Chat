<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  applyBrainRevisionBatch,
  createVersion,
  discardDraft,
  listVersions,
} from '../api'
import type { ResolvedRuntimeRequest } from '../utils/apiProfileStorage'
import { resolveRevisionPlan, revisionActionLabel } from '../utils/brainRevisionDisplay'
import {
  buildBrainRevisionBatchModules,
  canCreateBrainIteration,
  getMinorRevisionModules,
  linkedIssuesForModule,
  moduleLabel,
  pickForkBaseVersion,
  pickIterationVersionName,
} from '../utils/brainRevision'
import {
  brainRecommendationLabel,
  devPotentialLabel,
  type BrainModuleAdvice,
  type BrainParsed,
  type BrainRecommendation,
} from '../utils/parseBrainJson'

const props = defineProps<{
  parsed: BrainParsed
  apiConfig?: ResolvedRuntimeRequest | null
}>()

const router = useRouter()
const creatingIteration = ref(false)

const overallTagType = computed(() => {
  const map: Record<BrainRecommendation, 'success' | 'warning' | 'danger'> = {
    hold: 'success',
    minor: 'warning',
    major: 'danger',
  }
  return map[props.parsed.overall]
})

const minorModules = computed(() => getMinorRevisionModules(props.parsed))
const iterationVersionName = computed(() => pickIterationVersionName(props.parsed))
const canIterate = computed(() => canCreateBrainIteration(props.parsed))

function revisionPlanFor(mod: BrainModuleAdvice) {
  return resolveRevisionPlan(mod, linkedIssuesForModule(props.parsed, mod))
}

function goPromptManager(version?: string) {
  if (version) {
    void router.push({ path: '/', query: { version } })
  } else {
    void router.push('/')
  }
}

async function handleCreateAndIterate() {
  const versionName = iterationVersionName.value
  if (!versionName || !canIterate.value) {
    ElMessage.warning('智脑未给出可执行的小版本迭代建议')
    return
  }

  const cfg = props.apiConfig
  if (!cfg?.base_url?.trim() || !cfg.api_key?.trim() || !cfg.model?.trim()) {
    ElMessage.warning('请先在 API 配置页填写有效 API，才能执行 AI 迭代修订')
    return
  }

  const modules = buildBrainRevisionBatchModules(props.parsed)
  if (modules.length === 0) {
    ElMessage.warning('没有需要 AI 修订的模块')
    return
  }

  creatingIteration.value = true
  let draftCreated = false

  try {
    const catalog = await listVersions()
    const exists =
      catalog.baselines.includes(versionName) ||
      catalog.custom.some((v) => v.version === versionName) ||
      catalog.drafts.some((v) => v.version === versionName)
    if (exists) {
      ElMessage.warning(`版本 ${versionName} 已存在`)
      goPromptManager(versionName)
      return
    }

    const baseVersion = pickForkBaseVersion(props.parsed)
    await createVersion(versionName, baseVersion)
    draftCreated = true

    const result = await applyBrainRevisionBatch(versionName, {
      modules,
      base_url: cfg.base_url,
      api_key: cfg.api_key,
      model: cfg.model,
      temperature: cfg.temperature,
    })

    const revisedTypes = result.modules.map((m) => moduleLabel(m.prompt_type)).join('、')
    ElMessage.success(`已创建 ${versionName}，并完成 ${revisedTypes} 的 AI 迭代修订`)
    goPromptManager(versionName)
  } catch (error) {
    if (draftCreated) {
      try {
        await discardDraft(versionName)
      } catch {
        /* ignore */
      }
    }
    const msg = error instanceof Error ? error.message : 'AI 迭代修订失败'
    ElMessage.error(
      draftCreated
        ? `${msg}。未产生有效 SP 改动的草稿已自动丢弃。`
        : msg,
    )
  } finally {
    creatingIteration.value = false
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

    <div v-if="canIterate" class="brain-primary-action">
      <div class="brain-primary-copy">
        <div class="brain-primary-title">执行 SP 迭代</div>
        <p class="brain-primary-desc">
          将 fork <strong>{{ iterationVersionName }}</strong>，并对
          {{ minorModules.map((m) => moduleLabel(m.prompt_type)).join('、') }}
          根据测评结论与修订计划调用 AI 改写 SP。若未产生相对基线的有效改动，草稿不会保留。
        </p>
      </div>
      <el-button
        type="primary"
        :loading="creatingIteration"
        @click="handleCreateAndIterate"
      >
        创建 {{ iterationVersionName }} 并 AI 迭代
      </el-button>
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
        <el-tag
          :type="mod.recommendation === 'minor' ? 'warning' : mod.recommendation === 'major' ? 'danger' : 'success'"
          size="small"
        >
          {{ brainRecommendationLabel(mod.recommendation) }}
        </el-tag>
        <span class="brain-version-chip">被测 {{ mod.evaluated_version }}</span>
        <span v-if="mod.base_version" class="brain-version-chip">基线 {{ mod.base_version }}</span>
      </div>
      <p class="brain-rationale">{{ mod.rationale }}</p>
      <ul v-if="mod.focus_areas.length" class="brain-focus-list">
        <li v-for="(area, idx) in mod.focus_areas" :key="idx">{{ area }}</li>
      </ul>

      <div
        v-if="mod.recommendation === 'minor'"
        class="brain-revision-plan"
      >
        <div class="brain-revision-plan-title">AI 修订计划（创建时将逐条落实）</div>

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
          <p v-if="!revisionPlanFor(mod).sfw.length" class="brain-revision-empty">
            （修订计划由 focus_areas / 测评 issues 驱动）
          </p>
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
          <p v-if="!revisionPlanFor(mod).nsfw.length" class="brain-revision-empty">
            （修订计划由 focus_areas / 测评 issues 驱动）
          </p>
        </div>
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

.brain-primary-action {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid #d9ecff;
  border-radius: 8px;
  background: #ecf5ff;
}

.brain-primary-copy {
  flex: 1;
  min-width: 0;
}

.brain-primary-title {
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}

.brain-primary-desc {
  margin: 0;
  font-size: 12px;
  color: #606266;
  line-height: 1.55;
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
