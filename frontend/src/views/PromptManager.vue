<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  commitVersion,
  composePrompt,
  createVersion,
  deleteVersion,
  discardDraft,
  getVersionDoc,
  getVersionMeta,
  getVersionPrompt,
  listVersions,
  saveDraft,
  translateVersion,
  type PromptLang,
  type PromptType,
  type VersionMetaResponse,
} from '../api'
import { collectVersionSubtree, buildVersionTree, rootBaselineForVersion } from '../utils/versionTree'
const MarkdownViewer = defineAsyncComponent(
  () => import('../components/MarkdownViewer.vue'),
)
import PromptViewer from '../components/PromptViewer.vue'
import AdaptiveTabs from '../components/AdaptiveTabs.vue'
import {
  clearTranslateConfig,
  defaultTranslateConfig,
  hasSavedTranslateConfig,
  loadTranslateConfig,
  resolveTranslateConfig,
  saveTranslateConfig,
  type TranslateConfig,
} from '../utils/translateConfigStorage'
import { normalizeBaseUrl } from '../utils/apiConfigStorage'

const route = useRoute()
const baselineTab = ref<'v1' | 'v2'>('v2')
const activeVersion = ref('v2')
const versionNodes = ref<{ version: string; base_version: string; status?: string }[]>([])
const versionMeta = ref<VersionMetaResponse | null>(null)

const promptType = ref<PromptType>('segment_compress')
const lang = ref<PromptLang>('zh')
const promptPart = ref<'sfw' | 'nsfw' | 'preview'>('sfw')
const previewIncludeNsfw = ref(true)

const docContent = ref('')
const docFilename = ref('')
const baselineSfw = ref('')
const baselineNsfw = ref('')
const editSfw = ref('')
const editNsfw = ref('')

const loading = ref(false)
const savingDraft = ref(false)
const committing = ref(false)
const translating = ref(false)
const editingDoc = ref(false)
const draftDirty = ref(false)
const lastSavedAt = ref<string | null>(null)

const createDialogVisible = ref(false)
const createVersionName = ref('')
const createBaseVersion = ref<string>('')

const translateConfigExpanded = ref<string[]>([])
const translateConfig = ref<TranslateConfig>(loadTranslateConfig())
const translateFromFallback = ref(!hasSavedTranslateConfig())

let draftSaveTimer: ReturnType<typeof setTimeout> | null = null
let skipAutoSave = false

const baselineTabItems = [
  { label: 'v1', name: 'v1' },
  { label: 'v2', name: 'v2' },
]

const subVersionTree = computed(() => buildVersionTree(versionNodes.value, baselineTab.value))

const createBaseVersionOptions = computed(() => {
  const seen = new Set<string>()
  const options: { label: string; value: string }[] = []
  const add = (label: string, value: string) => {
    if (seen.has(value)) return
    seen.add(value)
    options.push({ label, value })
  }
  const current = activeVersion.value
  if (current !== 'v1' && current !== 'v2') {
    add(current, current)
  }
  add('v1', 'v1')
  add('v2', 'v2')
  add('不选择', '')
  return options
})

const promptPartItems = [
  { label: 'SFW', name: 'sfw' },
  { label: 'NSFW', name: 'nsfw' },
  { label: '拼接预览', name: 'preview' },
]

const isBaselineVersion = (version: string) => version === 'v1' || version === 'v2'

const isBaseline = computed(
  () => versionMeta.value?.is_baseline ?? isBaselineVersion(activeVersion.value),
)
const isDraft = computed(() => versionMeta.value?.is_draft ?? false)
const canEditPrompt = computed(() => isDraft.value)

const promptStatusTag = computed(() => {
  if (isBaseline.value) {
    return { text: '只读基线', type: 'info' as const }
  }
  if (versionMeta.value && !canEditPrompt.value) {
    return { text: '已提交（只读）', type: 'success' as const }
  }
  return null
})
const baseVersion = computed(() => versionMeta.value?.base_version ?? '')
const hasCompareBase = computed(() => Boolean(baseVersion.value))
const hasEn = computed(() => versionMeta.value?.has_en ?? false)
const enDisabled = computed(() => canEditPrompt.value && !hasEn.value && lang.value === 'en')

const assembledBaselinePreview = computed(() =>
  composePrompt(baselineSfw.value, baselineNsfw.value, previewIncludeNsfw.value),
)
const assembledEditPreview = computed(() =>
  composePrompt(editSfw.value, editNsfw.value, previewIncludeNsfw.value),
)

function scheduleDraftSave(payload: {
  prompt_type?: PromptType
  lang?: PromptLang
  content_sfw?: string
  content_nsfw?: string
  doc_content?: string
}) {
  if (!canEditPrompt.value || skipAutoSave) return
  draftDirty.value = true
  if (draftSaveTimer) clearTimeout(draftSaveTimer)
  draftSaveTimer = setTimeout(() => {
    void persistDraft(payload)
  }, 800)
}

async function persistDraft(payload: {
  prompt_type?: PromptType
  lang?: PromptLang
  content_sfw?: string
  content_nsfw?: string
  doc_content?: string
}) {
  if (!canEditPrompt.value) return
  savingDraft.value = true
  try {
    const result = await saveDraft(activeVersion.value, payload)
    lastSavedAt.value = result.updated_at
    draftDirty.value = false
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'Redis 草稿保存失败')
  } finally {
    savingDraft.value = false
  }
}

async function refreshVersionList() {
  try {
    const data = await listVersions()
    versionNodes.value = [...data.custom, ...data.drafts].map((item) => ({
      version: item.version,
      base_version: item.base_version,
      status: item.status,
    }))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载版本列表失败')
  }
}

function onSubVersionSelect(node: { version: string }) {
  activeVersion.value = node.version
}

function onBaselineTabClick(tab: string) {
  if (tab !== 'v1' && tab !== 'v2') return
  baselineTab.value = tab
  activeVersion.value = tab
}

function renderTreeNodeLabel(data: { version: string; status?: string }) {
  return data.status === 'draft' ? `${data.version}（草稿）` : data.version
}

async function loadVersionData() {
  loading.value = true
  skipAutoSave = true
  try {
    versionMeta.value = await getVersionMeta(activeVersion.value)
    if (lang.value === 'en' && !hasEn.value && canEditPrompt.value) {
      lang.value = 'zh'
    }

    const doc = await getVersionDoc(activeVersion.value)
    docContent.value = doc.content
    docFilename.value = doc.filename
    editingDoc.value = false

    const baseline = hasCompareBase.value
      ? await getVersionPrompt(baseVersion.value, promptType.value, lang.value)
      : null
    baselineSfw.value = baseline?.content_sfw ?? ''
    baselineNsfw.value = baseline?.content_nsfw ?? ''

    if (isBaseline.value) {
      editSfw.value = baselineSfw.value
      editNsfw.value = baselineNsfw.value
    } else {
      const current = await getVersionPrompt(activeVersion.value, promptType.value, lang.value)
      editSfw.value = current.content_sfw
      editNsfw.value = current.content_nsfw
    }
    draftDirty.value = false
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载提示词失败')
  } finally {
    loading.value = false
    setTimeout(() => {
      skipAutoSave = false
    }, 100)
  }
}

async function onVersionChange() {
  await loadVersionData()
}

async function onPromptContextChange() {
  await loadVersionData()
}

watch(activeVersion, onVersionChange)
watch([promptType, lang], onPromptContextChange)

watch(baselineTab, (tab) => {
  if (activeVersion.value !== tab) {
    activeVersion.value = tab
  }
})

watch(activeVersion, (version) => {
  if (version === 'v1' || version === 'v2') {
    if (baselineTab.value !== version) {
      baselineTab.value = version
    }
    return
  }
  const root = rootBaselineForVersion(versionNodes.value, version, baselineTab.value)
  if (baselineTab.value !== root) {
    baselineTab.value = root
  }
})

watch(editSfw, (value) => {
  scheduleDraftSave({
    prompt_type: promptType.value,
    lang: lang.value,
    content_sfw: value,
  })
})

watch(editNsfw, (value) => {
  scheduleDraftSave({
    prompt_type: promptType.value,
    lang: lang.value,
    content_nsfw: value,
  })
})

watch(docContent, (value) => {
  if (editingDoc.value) {
    scheduleDraftSave({ doc_content: value })
  }
})

watch(
  translateConfig,
  () => {
    saveTranslateConfig(translateConfig.value)
    translateFromFallback.value = false
  },
  { deep: true },
)

function openCreateDialog() {
  createVersionName.value = ''
  createBaseVersion.value = activeVersion.value
  createDialogVisible.value = true
}

async function confirmCreateVersion() {
  const version = createVersionName.value.trim()
  if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(version)) {
    ElMessage.warning('版本名以字母开头，仅允许字母、数字和下划线')
    return
  }
  if (version === 'v1' || version === 'v2') {
    ElMessage.warning('v1 / v2 为只读基线，请使用其他版本名')
    return
  }
  try {
    await createVersion(version, createBaseVersion.value || null)
    await refreshVersionList()
    activeVersion.value = version
    createDialogVisible.value = false
    ElMessage.success(`已创建草稿 ${version}`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '创建失败')
  }
}

async function commitToMysql() {
  committing.value = true
  try {
    await commitVersion(activeVersion.value)
    await refreshVersionList()
    versionMeta.value = await getVersionMeta(activeVersion.value)
    await loadVersionData()
    ElMessage.success('已保存到 MySQL')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '提交失败')
  } finally {
    committing.value = false
  }
}

async function runTranslate() {
  const cfg = resolveTranslateConfig()
  if (!cfg.base_url || !cfg.api_key || !cfg.model) {
    ElMessage.error('请配置翻译 API 或先在「API 配置」页保存 API 配置')
    return
  }
  translating.value = true
  try {
    await translateVersion(activeVersion.value, {
      base_url: normalizeBaseUrl(cfg.base_url),
      api_key: cfg.api_key,
      model: cfg.model,
      temperature: cfg.temperature,
    })
    versionMeta.value = await getVersionMeta(activeVersion.value)
    if (lang.value === 'en' || hasEn.value) {
      await loadVersionData()
    }
    ElMessage.success('英文 SP 已生成并写入 Redis 草稿')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '翻译失败')
  } finally {
    translating.value = false
  }
}

async function discardCurrentDraft() {
  try {
    await ElMessageBox.confirm(`确定丢弃 ${activeVersion.value} 的 Redis 草稿？`, '丢弃草稿', {
      type: 'warning',
    })
    await discardDraft(activeVersion.value)
    await refreshVersionList()
    activeVersion.value = baseVersion.value || 'v2'
    ElMessage.success('草稿已丢弃')
  } catch {
    // cancelled
  }
}

async function confirmDeleteVersion() {
  if (isBaseline.value) {
    ElMessage.warning('基线版本 v1 / v2 不可删除')
    return
  }
  const targets = collectVersionSubtree(versionNodes.value, activeVersion.value)
  const childVersions = targets.filter((item) => item !== activeVersion.value)
  const message =
    childVersions.length > 0
      ? `确定删除版本 ${activeVersion.value}？\n将一并删除 ${targets.length} 个版本（含子版本）：\n${targets.join('、')}`
      : `确定删除版本 ${activeVersion.value}？\n此操作不可恢复。`
  try {
    await ElMessageBox.confirm(message, '删除版本', {
      type: 'warning',
      confirmButtonText: '删除',
      confirmButtonClass: 'el-button--danger',
    })
    const fallback = baseVersion.value || 'v2'
    const result = await deleteVersion(activeVersion.value)
    await refreshVersionList()
    activeVersion.value = fallback === 'v1' || fallback === 'v2' ? fallback : rootBaselineForVersion(versionNodes.value, fallback, 'v2')
    const count = result.deleted.length
    ElMessage.success(count > 1 ? `已删除 ${count} 个版本` : '版本已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error instanceof Error ? error.message : '删除失败')
  }
}

function clearTranslateStorage() {
  clearTranslateConfig()
  translateConfig.value = { ...defaultTranslateConfig }
  translateFromFallback.value = true
  ElMessage.success('已清除翻译 API 本地配置')
}

onMounted(async () => {
  await refreshVersionList()
  const queryVersion = typeof route.query.version === 'string' ? route.query.version.trim() : ''
  if (queryVersion) {
    activeVersion.value = queryVersion
    const root = rootBaselineForVersion(versionNodes.value, queryVersion)
    if (root === 'v1' || root === 'v2') {
      baselineTab.value = root
    } else if (queryVersion === 'v1' || queryVersion === 'v2') {
      baselineTab.value = queryVersion
    }
  }
  await loadVersionData()
})
</script>

<template>
  <el-card class="page-card" shadow="never">
    <el-row :gutter="16" class="full-height">
      <el-col :span="5" class="full-height">
        <div class="panel">
          <div class="panel-title">
            <span>版本与文件</span>
            <div class="panel-title-actions">
              <el-button
                v-if="!isBaseline"
                size="small"
                type="danger"
                plain
                class="delete-btn"
                @click="confirmDeleteVersion"
              >
                删除
              </el-button>
              <el-button size="small" type="primary" plain class="add-btn" @click="openCreateDialog">
                +
              </el-button>
            </div>
          </div>
          <AdaptiveTabs
            v-model="baselineTab"
            :items="baselineTabItems"
            layout="stretch"
            @tab-click="onBaselineTabClick"
          />

          <div v-if="subVersionTree.length" class="sub-version-panel">
            <div class="switch-label">子版本</div>
            <el-tree
              :data="subVersionTree"
              node-key="version"
              :props="{ label: 'version', children: 'children' }"
              :expand-on-click-node="false"
              default-expand-all
              class="sub-version-tree"
              @node-click="onSubVersionSelect"
            >
              <template #default="{ node, data }">
                <span
                  class="version-tree-node"
                  :class="{ 'is-active': activeVersion === data.version }"
                  :style="node.level > 1 ? { marginLeft: `${(node.level - 1) * 16}px` } : undefined"
                >
                  {{ renderTreeNodeLabel(data) }}
                </span>
              </template>
            </el-tree>
          </div>

          <div class="type-switch">
            <div class="switch-label">类型</div>
            <el-radio-group v-model="promptType" size="small">
              <el-radio-button label="segment_compress">Segment 压缩</el-radio-button>
              <el-radio-button label="history_merge">History 合并</el-radio-button>
            </el-radio-group>
          </div>

          <div class="type-switch">
            <div class="switch-label">语言</div>
            <el-radio-group v-model="lang" size="small">
              <el-radio-button label="zh">中文</el-radio-button>
              <el-radio-button
                label="en"
                :disabled="enDisabled"
              >
                English
              </el-radio-button>
            </el-radio-group>
            <p v-if="enDisabled" class="lang-hint">请先翻译生成英文</p>
          </div>
        </div>
      </el-col>

      <el-col :span="9" class="full-height">
        <div class="panel">
          <div class="panel-title">
            <span>版本文档</span>
            <el-tag v-if="docFilename" size="small" type="info">{{ docFilename }}</el-tag>
            <el-tag v-if="isDraft" size="small" type="warning">未保存到 MySQL</el-tag>
            <el-tag v-if="savingDraft" size="small">保存 Redis 中…</el-tag>
            <div v-if="canEditPrompt" class="panel-actions">
              <el-button size="small" @click="editingDoc = !editingDoc">
                {{ editingDoc ? '预览' : '编辑' }}
              </el-button>
            </div>
          </div>
          <div v-loading="loading" class="doc-body">
            <el-scrollbar v-if="isBaseline || !editingDoc" class="doc-scroll">
              <MarkdownViewer :content="docContent" />
            </el-scrollbar>
            <el-input
              v-else
              v-model="docContent"
              type="textarea"
              class="doc-editor"
              placeholder="Markdown 文档内容"
            />
          </div>
        </div>
      </el-col>

      <el-col :span="10" class="full-height">
        <div class="panel">
          <div class="panel-title">
            <div class="panel-title-leading">
              <span class="panel-title-text">System Prompt 正文</span>
              <span v-if="promptStatusTag" class="panel-status-tag">
                <el-tag size="small" :type="promptStatusTag.type">{{ promptStatusTag.text }}</el-tag>
              </span>
            </div>
          </div>

          <div v-loading="loading" class="prompt-wrap">
            <AdaptiveTabs v-model="promptPart" :items="promptPartItems" layout="stretch" />

            <div v-if="isBaseline" class="single-prompt">
              <PromptViewer
                v-if="promptPart === 'sfw'"
                :model-value="baselineSfw"
                :filename="`${activeVersion} · SFW`"
                readonly
              />
              <PromptViewer
                v-else-if="promptPart === 'nsfw'"
                :model-value="baselineNsfw"
                :filename="`${activeVersion} · NSFW`"
                readonly
              />
              <div v-else class="preview-panel">
                <div class="preview-toolbar">
                  <el-switch
                    v-model="previewIncludeNsfw"
                    active-text="含 NSFW"
                    inactive-text="仅 SFW"
                  />
                </div>
                <el-scrollbar class="preview-scroll">
                  <pre class="prompt-pre">{{ assembledBaselinePreview || '暂无内容' }}</pre>
                </el-scrollbar>
              </div>
            </div>

            <div v-else :class="['compare-prompt', { 'compare-prompt--single': !hasCompareBase }]">
              <div v-if="hasCompareBase" class="compare-col">
                <div class="compare-header">基线 {{ baseVersion }}（只读）</div>
                <PromptViewer
                  v-if="promptPart === 'sfw'"
                  :model-value="baselineSfw"
                  readonly
                />
                <PromptViewer
                  v-else-if="promptPart === 'nsfw'"
                  :model-value="baselineNsfw"
                  readonly
                />
                <div v-else class="preview-panel">
                  <el-scrollbar class="preview-scroll">
                    <pre class="prompt-pre">{{ assembledBaselinePreview || '暂无内容' }}</pre>
                  </el-scrollbar>
                </div>
              </div>
              <div class="compare-col">
                <div class="compare-header">
                  {{ canEditPrompt ? `新版本 ${activeVersion}` : `版本 ${activeVersion}（只读）` }}
                </div>
                <PromptViewer
                  v-if="promptPart === 'sfw'"
                  v-model="editSfw"
                  :filename="`${activeVersion} · SFW`"
                  :readonly="!canEditPrompt"
                  :show-save="false"
                />
                <PromptViewer
                  v-else-if="promptPart === 'nsfw'"
                  v-model="editNsfw"
                  :filename="`${activeVersion} · NSFW`"
                  :readonly="!canEditPrompt"
                  :show-save="false"
                />
                <div v-else class="preview-panel">
                  <div class="preview-toolbar">
                    <el-switch
                      v-model="previewIncludeNsfw"
                      active-text="含 NSFW"
                      inactive-text="仅 SFW"
                    />
                  </div>
                  <el-scrollbar class="preview-scroll">
                    <pre class="prompt-pre">{{ assembledEditPreview || '暂无内容' }}</pre>
                  </el-scrollbar>
                </div>
              </div>
            </div>
          </div>

          <div v-if="canEditPrompt" class="action-bar">
            <el-collapse v-model="translateConfigExpanded">
              <el-collapse-item name="translate-config">
                <template #title>
                  <span>翻译 API 配置</span>
                  <el-tag v-if="translateFromFallback" size="small" type="info" class="fallback-tag">
                    未配置，将使用 API 配置页第一个 Profile
                  </el-tag>
                </template>
                <el-form label-width="100px" class="translate-form">
                  <el-form-item label="BASE_URL">
                    <el-input v-model="translateConfig.base_url" placeholder="留空则 fallback 至 API 配置页第一个 Profile" />
                  </el-form-item>
                  <el-form-item label="API_KEY">
                    <el-input v-model="translateConfig.api_key" type="password" show-password />
                  </el-form-item>
                  <el-form-item label="model">
                    <el-input v-model="translateConfig.model" />
                  </el-form-item>
                  <el-form-item label="temperature">
                    <el-input-number v-model="translateConfig.temperature" :min="0" :max="2" :step="0.1" />
                  </el-form-item>
                  <el-form-item>
                    <el-button @click="clearTranslateStorage">清除本地配置</el-button>
                  </el-form-item>
                </el-form>
              </el-collapse-item>
            </el-collapse>

            <div class="action-buttons">
              <el-button :loading="translating" @click="runTranslate">翻译生成英文</el-button>
              <el-button v-if="isDraft" type="danger" plain @click="discardCurrentDraft">
                丢弃草稿
              </el-button>
              <el-button type="primary" :loading="committing" @click="commitToMysql">
                保存到 MySQL
              </el-button>
              <span v-if="lastSavedAt" class="save-hint">Redis 已同步 · {{ lastSavedAt }}</span>
              <span v-else-if="draftDirty" class="save-hint">有未同步修改…</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-dialog v-model="createDialogVisible" title="新建自定义版本" width="460px">
      <el-form label-width="110px">
        <el-form-item label="版本名" required>
          <el-input
            v-model="createVersionName"
            placeholder="如 v3、v3_myedit、v2_myedit"
          />
          <p class="dialog-hint">以字母开头，仅允许 [a-zA-Z0-9_]，不可使用 v1 / v2</p>
        </el-form-item>
        <el-form-item label="基线版本">
          <el-radio-group v-model="createBaseVersion">
            <el-radio
              v-for="opt in createBaseVersionOptions"
              :key="opt.value || '__empty__'"
              :label="opt.value"
            >
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
          <p class="dialog-hint">选择基线时将复制其中文 SP 与文档；不选择则创建空白草稿</p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmCreateVersion">创建</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.page-card {
  border: none;
}

.page-card :deep(.el-card__body) {
  height: 100%;
  padding: 0;
}

.panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  padding: 12px 14px;
  font-weight: 600;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
}

.panel-title-leading {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  flex-wrap: nowrap;
  gap: 8px;
  min-width: 0;
}

.panel-title-text {
  flex-shrink: 0;
}

.panel-status-tag {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  flex-shrink: 0;
  line-height: 1;
}

.panel-status-tag :deep(.el-tag) {
  justify-content: flex-start;
}

.add-btn {
  min-width: 32px;
  padding: 0 10px;
}

.panel-title-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.delete-btn {
  padding: 0 10px;
}

.panel-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.type-switch {
  padding: 10px 14px;
  border-top: 1px solid #f0f2f5;
}

.sub-version-panel {
  padding: 10px 14px 0;
  border-top: 1px solid #f0f2f5;
}

.sub-version-tree {
  max-height: 200px;
  overflow: auto;
}

.sub-version-tree :deep(.el-tree-node__content) {
  height: auto;
  min-height: 32px;
  padding-top: 2px;
  padding-bottom: 2px;
  padding-left: 0 !important;
  background: transparent !important;
}

.sub-version-tree :deep(.el-tree-node__children) {
  padding-left: 0;
}

.sub-version-tree :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: transparent !important;
}

.sub-version-tree :deep(.el-tree-node__expand-icon.is-leaf) {
  display: none;
}

.sub-version-tree :deep(.el-tree-node__expand-icon:not(.is-leaf)) {
  margin-right: 4px;
  padding: 0;
}

.sub-version-tree :deep(.el-tree-node__expand-icon) {
  color: #909399;
}

.version-tree-node {
  display: inline-flex;
  align-items: center;
  width: 100%;
  max-width: 100%;
  min-height: 24px;
  padding: 5px 12px;
  font-size: 12px;
  line-height: 1;
  border: 1px solid var(--el-border-color);
  border-radius: 0;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-regular);
  box-sizing: border-box;
}

.version-tree-node.is-active {
  background-color: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: #fff;
}

.switch-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.lang-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #e6a23c;
}

.doc-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.doc-scroll {
  flex: 1;
  padding: 14px;
}

.doc-editor {
  flex: 1;
  min-height: 0;
  padding: 14px;
  display: flex;
  flex-direction: column;
}

.doc-editor :deep(.el-textarea) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.doc-editor :deep(.el-textarea__inner) {
  flex: 1;
  height: 100% !important;
  min-height: 100%;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
  resize: none;
}

.prompt-wrap {
  flex: 1;
  min-height: 0;
  padding: 8px;
  display: flex;
  flex-direction: column;
}

.single-prompt,
.compare-prompt {
  flex: 1;
  min-height: 0;
  min-width: 0;
  width: 100%;
  display: flex;
}

.single-prompt {
  flex-direction: column;
}

.single-prompt :deep(.prompt-viewer),
.single-prompt .preview-panel {
  flex: 1;
  width: 100%;
  min-height: 0;
}

.compare-prompt {
  gap: 8px;
  flex-direction: row;
}

.compare-prompt--single .compare-col {
  flex: 1;
  width: 100%;
}

.compare-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.compare-col :deep(.prompt-viewer),
.compare-col .preview-panel {
  flex: 1;
  width: 100%;
  min-height: 0;
}

.compare-header {
  font-size: 12px;
  color: #606266;
  padding: 4px 4px 8px;
  font-weight: 500;
}

.preview-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
}

.preview-toolbar {
  padding: 10px 14px;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
}

.preview-scroll {
  flex: 1;
  padding: 14px;
}

.action-bar {
  border-top: 1px solid #ebeef5;
  padding: 8px 12px 12px;
  background: #fafafa;
}

.action-buttons {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.save-hint {
  font-size: 12px;
  color: #909399;
}

.translate-form {
  max-width: 100%;
}

.fallback-tag {
  margin-left: 8px;
}

.dialog-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #909399;
}

.prompt-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
}
</style>
