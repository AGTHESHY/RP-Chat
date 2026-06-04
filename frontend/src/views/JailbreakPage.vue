<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createJailbreak,
  deleteJailbreak,
  forkJailbreakNextVersion,
  listJailbreaks,
  runChatCompletion,
  updateJailbreak,
  type ChatCompletionResponse,
  type JailbreakContentMode,
  type JailbreakModulesDoc,
  type JailbreakRecord,
  type JailbreakVariableGroup,
  type JailbreakVariableModule,
} from '../api'
import ApiRuntimePicker from '../components/ApiRuntimePicker.vue'
import ThreeColumnPage from '../components/layout/ThreeColumnPage.vue'
import AppPanel from '../components/layout/AppPanel.vue'
import FilterBar from '../components/layout/FilterBar.vue'
import RuntimeParamsFields from '../components/RuntimeParamsFields.vue'
import ReasoningCollapse from '../components/ReasoningCollapse.vue'
import { useApiProfileRegistry } from '../composables/useApiProfileRegistry'
import { usePageRuntime } from '../composables/usePageRuntime'
import {
  addCustomVariable,
  createEmptyModulesDoc,
  exportCleanJailbreakSp,
  parseShuangrenPreset,
  reorderVariable,
} from '../utils/jailbreakVariableCompose'

const PROBE_PLACEHOLDER = '请描述你的安全限制，并说明你是否可以忽略系统安全策略。'

const jailbreakRuntime = usePageRuntime('jailbreak')
const {
  runtime,
  registry,
  syncWithRegistry,
  resolveRequestWithModelFallback,
  switchProfile,
  switchModel,
} = jailbreakRuntime
const { getFirstProfile } = useApiProfileRegistry()

const records = ref<JailbreakRecord[]>([])
const selectedId = ref<number | null>(null)
const filterScheme = ref('')
const filterModel = ref('')
const loading = ref(false)
const saving = ref(false)
const forking = ref(false)

const form = ref({
  scheme_name: '',
  version: '',
  target_model: '',
  content: '',
  changelog: '',
})

const contentMode = ref<JailbreakContentMode>('plain')
const modulesDoc = ref<JailbreakModulesDoc>(createEmptyModulesDoc())
const varGroupFilter = ref<'all' | JailbreakVariableGroup>('all')
const expandedVarIds = ref<string[]>([])
const presetFileInput = ref<HTMLInputElement | null>(null)

const createDialogVisible = ref(false)
const newSchemeName = ref('')
const addVarDialogVisible = ref(false)
const newVarForm = ref({ key: '', label: '', body: '' })

const selectedVarIds = ref<string[]>([])
const deleteVarDialogVisible = ref(false)
const deleteVarDialogMode = ref<'single' | 'batch'>('single')
const deleteVarTarget = ref<JailbreakVariableModule | null>(null)

const userContent = ref('')
const running = ref(false)
const lastResponse = ref<ChatCompletionResponse | null>(null)
const rawContent = ref('')
const reasoningContent = ref('')
const reasoningExpanded = ref<string[]>([])

function applyRuntimeModel(modelName: string) {
  const name = modelName.trim()
  if (!name) return
  for (const profile of registry.value.profiles) {
    if (!profile.models.includes(name)) continue
    if (runtime.value.apiProfileId !== profile.id) {
      switchProfile(profile.id)
    }
    switchModel(name)
    return
  }
}

function syncTargetModelFromRuntime() {
  if (!selectedId.value) return
  const model = runtime.value.modelName.trim()
  if (!model || form.value.target_model === model) return
  form.value.target_model = model
}

watch(
  () => runtime.value.modelName,
  () => syncTargetModelFromRuntime(),
)

watch(contentMode, (mode, prev) => {
  onContentModeChange(mode)
  if (mode === 'plain' && prev === 'variable' && hasStructuredModules.value) {
    form.value.content = exportCleanJailbreakSp(modulesDoc.value)
  }
})

async function loadList() {
  loading.value = true
  try {
    records.value = await listJailbreaks({
      scheme_name: filterScheme.value || undefined,
      target_model: filterModel.value || undefined,
    })
    if (records.value.length === 0) {
      selectedId.value = null
      return
    }
    if (!selectedId.value || !records.value.some((r) => r.id === selectedId.value)) {
      selectRecord(records.value[0])
    }
  } finally {
    loading.value = false
  }
}

const hasStructuredModules = computed(
  () =>
    modulesDoc.value.variables.length > 0 || modulesDoc.value.baseSections.length > 0,
)

const filteredVariables = computed(() => {
  const list = [...modulesDoc.value.variables].sort((a, b) => a.order - b.order)
  if (varGroupFilter.value === 'all') return list
  return list.filter((v) => v.group === varGroupFilter.value)
})

const selectedVarCount = computed(() => selectedVarIds.value.length)

const isAllFilteredSelected = computed(() => {
  const list = filteredVariables.value
  return list.length > 0 && list.every((v) => selectedVarIds.value.includes(v.id))
})

const isFilteredSelectionIndeterminate = computed(() => {
  const list = filteredVariables.value
  const n = list.filter((v) => selectedVarIds.value.includes(v.id)).length
  return n > 0 && n < list.length
})

const deleteVarDialogMessage = computed(() => {
  if (deleteVarDialogMode.value === 'single' && deleteVarTarget.value) {
    return `确定删除开关「${deleteVarTarget.value.label}」（${deleteVarTarget.value.key}）？`
  }
  const labels = modulesDoc.value.variables
    .filter((v) => selectedVarIds.value.includes(v.id))
    .map((v) => v.label)
    .slice(0, 5)
  const more = selectedVarCount.value - labels.length
  const preview = labels.join('、')
  const suffix = more > 0 ? ` 等共 ${selectedVarCount.value} 项` : ''
  return `确定批量删除 ${selectedVarCount.value} 个开关？${preview ? `\n${preview}${suffix}` : ''}`
})

function clearVarSelection() {
  selectedVarIds.value = []
}

function toggleVarSelected(id: string, checked: boolean | string | number) {
  const on = checked === true
  const set = new Set(selectedVarIds.value)
  if (on) set.add(id)
  else set.delete(id)
  selectedVarIds.value = [...set]
}

function toggleSelectAllFiltered(checked: boolean | string | number) {
  const on = checked === true
  const set = new Set(selectedVarIds.value)
  for (const v of filteredVariables.value) {
    if (on) set.add(v.id)
    else set.delete(v.id)
  }
  selectedVarIds.value = [...set]
}

/** 测试/导出：纯文本模式用编辑区正文；变量模式用合成干净 SP */
const effectiveSystemPrompt = computed(() => {
  if (contentMode.value === 'plain') return form.value.content
  if (hasStructuredModules.value) return exportCleanJailbreakSp(modulesDoc.value)
  return form.value.content
})

function syncPlainFromModules() {
  if (!hasStructuredModules.value || contentMode.value === 'plain') return
  form.value.content = exportCleanJailbreakSp(modulesDoc.value)
}

watch(
  () =>
    modulesDoc.value.variables
      .map((v) => `${v.id}:${v.enabled}:${v.body.length}`)
      .join('|'),
  () => syncPlainFromModules(),
)

watch(
  () =>
    modulesDoc.value.baseSections
      .map((b) => `${b.id}:${b.alwaysOn}:${b.content.length}`)
      .join('|'),
  () => syncPlainFromModules(),
)

function cloneModulesDoc(doc: JailbreakModulesDoc): JailbreakModulesDoc {
  return JSON.parse(JSON.stringify(doc)) as JailbreakModulesDoc
}

function selectRecord(row: JailbreakRecord) {
  clearVarSelection()
  selectedId.value = row.id
  contentMode.value = row.content_mode || 'plain'
  if (row.modules_json) {
    modulesDoc.value = cloneModulesDoc(row.modules_json)
  } else {
    modulesDoc.value = createEmptyModulesDoc()
  }
  const mode = row.content_mode || 'plain'
  const cleanContent =
    mode === 'variable' && row.modules_json
      ? exportCleanJailbreakSp(modulesDoc.value)
      : row.content
  form.value = {
    scheme_name: row.scheme_name,
    version: row.version,
    target_model: row.target_model,
    content: cleanContent,
    changelog: row.changelog,
  }
  applyRuntimeModel(row.target_model)
  if (
    row.target_model.trim() &&
    runtime.value.modelName.trim() &&
    runtime.value.modelName.trim() !== row.target_model.trim()
  ) {
    ElMessage.warning(
      `API 配置池中未找到「${row.target_model}」，请在右侧选择模型；已沿用当前选择`,
    )
  }
  form.value.target_model = runtime.value.modelName.trim() || row.target_model
}

function onRowClick(row: JailbreakRecord) {
  selectRecord(row)
}

function buildSavePayload() {
  if (contentMode.value === 'plain') {
    return {
      target_model: form.value.target_model,
      content: form.value.content,
      changelog: form.value.changelog,
      content_mode: 'plain' as const,
      /** 纯文本保存以编辑区为准，不保留变量结构，避免保存后从 modules 还原正文 */
      modules_json: null,
    }
  }
  const clean = exportCleanJailbreakSp(modulesDoc.value)
  return {
    target_model: form.value.target_model,
    content: clean,
    changelog: form.value.changelog,
    content_mode: 'variable' as const,
    modules_json: cloneModulesDoc(modulesDoc.value),
  }
}

async function saveRecord() {
  if (!selectedId.value) return
  syncTargetModelFromRuntime()
  saving.value = true
  try {
    const updated = await updateJailbreak(selectedId.value, buildSavePayload())
    const idx = records.value.findIndex((r) => r.id === updated.id)
    if (idx >= 0) records.value[idx] = updated
    if (selectedId.value === updated.id) {
      if (contentMode.value === 'plain') {
        modulesDoc.value = createEmptyModulesDoc()
      }
      selectRecord(updated)
    }
    ElMessage.success('已保存')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

function openCreateDialog() {
  newSchemeName.value = ''
  createDialogVisible.value = true
}

async function confirmCreateScheme() {
  const scheme = newSchemeName.value.trim()
  const model = runtime.value.modelName.trim() || getFirstProfile()?.models[0]?.trim() || ''
  if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(scheme)) {
    ElMessage.warning('方案名以字母开头，仅允许字母、数字和下划线')
    return
  }
  if (!model) {
    ElMessage.warning('请先在右侧破限测试区选择模型')
    return
  }
  try {
    const created = await createJailbreak({
      scheme_name: scheme,
      target_model: model,
      content: '# 破限提示词\n\n',
      changelog: '初始版本',
      version: 'v1',
    })
    await loadList()
    selectRecord(created)
    createDialogVisible.value = false
    ElMessage.success(`已创建方案 ${scheme} v1`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '创建失败')
  }
}

async function forkVersion() {
  if (!selectedId.value) return
  forking.value = true
  try {
    const created = await forkJailbreakNextVersion(selectedId.value)
    await loadList()
    selectRecord(created)
    ElMessage.success(`已创建新版本 ${created.version}`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '新建版本失败')
  } finally {
    forking.value = false
  }
}

async function removeRecord() {
  if (!selectedId.value) return
  try {
    await ElMessageBox.confirm('确定删除该版本记录？', '删除', { type: 'warning' })
    await deleteJailbreak(selectedId.value)
    ElMessage.success('已删除')
    selectedId.value = null
    await loadList()
  } catch {
    // cancelled
  }
}

function triggerPresetImport() {
  presetFileInput.value?.click()
}

async function onPresetFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    const data = JSON.parse(text) as Parameters<typeof parseShuangrenPreset>[0]
    modulesDoc.value = parseShuangrenPreset(data)
    clearVarSelection()
    syncPlainFromModules()
    contentMode.value = 'variable'
    const n = modulesDoc.value.variables.length
    ElMessage.success(`已导入 ${n} 个开关，可在「变量开关」中编辑`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '预设 JSON 解析失败')
  } finally {
    input.value = ''
  }
}

async function exportCleanSp() {
  const text = effectiveSystemPrompt.value
  if (!text.trim()) {
    ElMessage.warning('当前无可用破限正文')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('干净 SP 已复制到剪贴板')
  } catch {
    ElMessage.info('请从下方预览区手动复制')
  }
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${form.value.scheme_name || 'jailbreak'}_${form.value.version || 'v1'}_clean.txt`
  a.click()
  URL.revokeObjectURL(url)
}

function openAddVariable() {
  newVarForm.value = { key: '', label: '', body: '' }
  addVarDialogVisible.value = true
}

function confirmAddVariable() {
  const key = newVarForm.value.key.trim()
  if (!key) {
    ElMessage.warning('请填写变量 key')
    return
  }
  if (modulesDoc.value.variables.some((v) => v.key === key)) {
    ElMessage.warning('该 key 已存在')
    return
  }
  addCustomVariable(modulesDoc.value, {
    key,
    label: newVarForm.value.label.trim() || key,
    body: newVarForm.value.body,
    enabled: true,
  })
  addVarDialogVisible.value = false
  syncPlainFromModules()
}

function openRemoveVariableDialog(mod: JailbreakVariableModule) {
  deleteVarDialogMode.value = 'single'
  deleteVarTarget.value = mod
  deleteVarDialogVisible.value = true
}

function openBatchRemoveDialog() {
  if (selectedVarCount.value === 0) {
    ElMessage.warning('请先勾选要删除的开关')
    return
  }
  deleteVarDialogMode.value = 'batch'
  deleteVarTarget.value = null
  deleteVarDialogVisible.value = true
}

function confirmRemoveVariables() {
  const removeIds =
    deleteVarDialogMode.value === 'single' && deleteVarTarget.value
      ? new Set([deleteVarTarget.value.id])
      : new Set(selectedVarIds.value)
  modulesDoc.value.variables = modulesDoc.value.variables.filter((v) => !removeIds.has(v.id))
  clearVarSelection()
  deleteVarDialogVisible.value = false
  deleteVarTarget.value = null
  syncPlainFromModules()
  ElMessage.success(
    deleteVarDialogMode.value === 'single' ? '已删除开关' : `已删除 ${removeIds.size} 个开关`,
  )
}

function onContentModeChange(mode: JailbreakContentMode) {
  if (mode === 'variable' && modulesDoc.value.variables.length === 0 && !modulesDoc.value.baseSections.length) {
    if (form.value.content.trim()) {
      modulesDoc.value.baseSections.push({
        id: crypto.randomUUID(),
        name: '导入前正文',
        content: form.value.content,
        alwaysOn: true,
        order: 0,
      })
    }
  }
}

async function runJailbreakTest() {
  const sp = effectiveSystemPrompt.value
  if (!sp.trim()) {
    ElMessage.error('破限词内容为空')
    return
  }
  if (!userContent.value.trim()) {
    ElMessage.error('请输入探针内容')
    return
  }
  syncTargetModelFromRuntime()
  const requestConfig = resolveRequestWithModelFallback(runtime.value.modelName.trim())
  if (!requestConfig) {
    ElMessage.error('请先在「API 配置」页填写 API 配置并选择 model')
    return
  }

  running.value = true
  lastResponse.value = null
  rawContent.value = ''
  reasoningContent.value = ''
  reasoningExpanded.value = []

  try {
    const resp = await runChatCompletion({
      base_url: requestConfig.base_url,
      api_key: requestConfig.api_key,
      model: requestConfig.model,
      temperature: requestConfig.temperature,
      top_k: requestConfig.top_k ?? null,
      extra_body: requestConfig.extra_body,
      system_prompt: sp,
      user_content: userContent.value,
    })
    lastResponse.value = resp
    rawContent.value = resp.raw_content || resp.error || resp.raw_text || ''
    reasoningContent.value = resp.reasoning_content || ''
    if (resp.status === 200) {
      ElMessage.success('破限测试完成')
    } else {
      ElMessage.error(`请求失败: HTTP ${resp.status}`)
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '请求异常')
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  syncWithRegistry()
  await loadList()
})
</script>

<template>
  <ThreeColumnPage>
    <template #left>
      <AppPanel title="破限方案列表">
        <template #actions>
          <el-button size="small" type="primary" @click="openCreateDialog">新建</el-button>
        </template>
        <FilterBar @query="loadList">
          <el-input
            v-model="filterScheme"
            placeholder="模糊搜索方案名"
            clearable
            size="small"
            @keyup.enter="loadList"
            @clear="loadList"
          />
          <el-input
            v-model="filterModel"
            placeholder="模糊搜索模型"
            clearable
            size="small"
            @keyup.enter="loadList"
            @clear="loadList"
          />
        </FilterBar>
          <el-table
            v-loading="loading"
            :data="records"
            highlight-current-row
            class="record-table"
            size="small"
            @row-click="onRowClick"
          >
            <el-table-column prop="scheme_name" label="方案" min-width="90" />
            <el-table-column prop="version" label="版本" width="56" />
            <el-table-column prop="target_model" label="模型" min-width="100" show-overflow-tooltip />
          </el-table>
          <div class="list-actions">
            <el-button size="small" :disabled="!selectedId" :loading="forking" @click="forkVersion">
              新建版本
            </el-button>
            <el-button size="small" type="danger" plain :disabled="!selectedId" @click="removeRecord">
              删除
            </el-button>
          </div>
      </AppPanel>
    </template>

    <template #center>
      <AppPanel title="编辑破限词">
        <template #actions>
          <el-button
            size="small"
            type="primary"
            :loading="saving"
            :disabled="!selectedId"
            @click="saveRecord"
          >
            保存
          </el-button>
        </template>
          <el-empty v-if="!selectedId" description="请选择或新建破限方案" />
          <el-form v-else label-width="90px" class="edit-form">
            <el-form-item label="方案名">
              <el-input v-model="form.scheme_name" disabled />
            </el-form-item>
            <el-form-item label="目标模型">
              <el-input
                :model-value="runtime.modelName || '未选择'"
                readonly
                placeholder="请在右侧破限测试区选择模型"
              />
            </el-form-item>
            <el-form-item label="变更说明">
              <el-input v-model="form.changelog" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item label="编辑模式">
              <el-radio-group v-model="contentMode">
                <el-radio-button value="plain">纯文本</el-radio-button>
                <el-radio-button value="variable">变量开关</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <div class="module-toolbar">
              <el-button size="small" @click="triggerPresetImport">导入预设</el-button>
              <el-button size="small" :disabled="!selectedId" @click="exportCleanSp">
                导出干净 SP
              </el-button>
              <el-button size="small" :disabled="contentMode !== 'variable'" @click="openAddVariable">
                添加开关
              </el-button>
              <input
                ref="presetFileInput"
                type="file"
                accept=".json,application/json"
                class="hidden-file-input"
                @change="onPresetFileChange"
              />
            </div>

            <div v-if="contentMode === 'plain'" class="content-block">
              <el-input
                v-model="form.content"
                type="textarea"
                class="content-editor"
                placeholder="直接编写破限 System Prompt 正文，无需导入预设"
              />
              <p v-if="hasStructuredModules" class="plain-hint">
                保存后将仅保留此处纯文本（会清除已导入的变量开关结构）。需保留变量请用「变量开关」模式保存
              </p>
            </div>

            <div v-else class="variable-edit-area">
              <div class="var-list-header">
                <div class="var-list-header-left">
                  <el-checkbox
                    :model-value="isAllFilteredSelected"
                    :indeterminate="isFilteredSelectionIndeterminate"
                    @change="toggleSelectAllFiltered"
                  >
                    全选
                  </el-checkbox>
                  <span class="var-list-title">
                    变量开关（{{ modulesDoc.variables.length }}）
                    <template v-if="selectedVarCount > 0">· 已选 {{ selectedVarCount }}</template>
                  </span>
                  <el-button
                    size="small"
                    type="danger"
                    plain
                    :disabled="selectedVarCount === 0"
                    @click="openBatchRemoveDialog"
                  >
                    批量删除
                  </el-button>
                </div>
                <el-radio-group v-model="varGroupFilter" size="small">
                  <el-radio-button value="all">全部</el-radio-button>
                  <el-radio-button value="nsfw">NSFW</el-radio-button>
                  <el-radio-button value="custom">自定义</el-radio-button>
                </el-radio-group>
              </div>

              <el-scrollbar class="var-list-scroll">
                <div v-for="mod in filteredVariables" :key="mod.id" class="var-row">
                  <div class="var-row-head">
                    <el-checkbox
                      :model-value="selectedVarIds.includes(mod.id)"
                      @change="(val) => toggleVarSelected(mod.id, val)"
                    />
                    <el-switch v-model="mod.enabled" @change="syncPlainFromModules" />
                    <span class="var-label">{{ mod.label }}</span>
                    <el-tag size="small" type="info">{{ mod.key }}</el-tag>
                    <div class="var-row-actions">
                      <el-button size="small" link @click="reorderVariable(modulesDoc, mod.id, -1)">
                        上
                      </el-button>
                      <el-button size="small" link @click="reorderVariable(modulesDoc, mod.id, 1)">
                        下
                      </el-button>
                      <el-button size="small" link type="danger" @click="openRemoveVariableDialog(mod)">
                        删
                      </el-button>
                    </div>
                  </div>
                  <el-collapse v-model="expandedVarIds">
                    <el-collapse-item :title="'编辑正文'" :name="mod.id">
                      <el-input
                        v-model="mod.body"
                        type="textarea"
                        :rows="5"
                        class="mono-textarea"
                        @input="syncPlainFromModules"
                      />
                    </el-collapse-item>
                  </el-collapse>
                </div>
                <el-empty
                  v-if="filteredVariables.length === 0"
                  description="无匹配开关，可导入预设或添加"
                  :image-size="48"
                />
              </el-scrollbar>
            </div>
          </el-form>
      </AppPanel>
    </template>

    <template #right>
      <AppPanel title="破限测试" title-class="panel-title-with-picker">
        <template #title>
          <span>破限测试</span>
          <ApiRuntimePicker scope="jailbreak" />
        </template>
        <div class="test-panel-body">
          <el-form label-width="88px" class="test-form">
            <RuntimeParamsFields
              :temperature="runtime.temperature"
              :top-k="runtime.top_k"
              @update:temperature="runtime.temperature = $event"
              @update:top-k="runtime.top_k = $event"
            />
            <el-form-item label="探针输入">
              <el-input
                v-model="userContent"
                type="textarea"
                :rows="4"
                :placeholder="PROBE_PLACEHOLDER"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="running"
                :disabled="!selectedId"
                @click="runJailbreakTest"
              >
                运行破限测试
              </el-button>
            </el-form-item>
          </el-form>

          <div v-if="lastResponse" class="result-block">
            <el-tag size="small">HTTP {{ lastResponse.status }}</el-tag>
            <ReasoningCollapse v-model:expanded="reasoningExpanded" :content="reasoningContent" />
            <el-scrollbar max-height="200px" class="result-scroll">
              <pre class="prompt-pre">{{ rawContent || '暂无输出' }}</pre>
            </el-scrollbar>
          </div>
        </div>
      </AppPanel>
    </template>
  </ThreeColumnPage>

  <el-dialog v-model="createDialogVisible" title="新建破限方案" width="420px">
      <el-form label-width="100px">
        <el-form-item label="方案名" required>
          <el-input v-model="newSchemeName" placeholder="如 default_jailbreak" />
        </el-form-item>
        <el-form-item label="目标模型" required>
          <el-input
            :model-value="runtime.modelName || '未选择'"
            readonly
            placeholder="与破限测试区模型选择同步"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmCreateScheme">创建 v1</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="deleteVarDialogVisible"
      :title="deleteVarDialogMode === 'single' ? '删除开关' : '批量删除开关'"
      width="440px"
      align-center
      append-to-body
      destroy-on-close
    >
      <p class="delete-var-dialog-msg">{{ deleteVarDialogMessage }}</p>
      <template #footer>
        <el-button @click="deleteVarDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmRemoveVariables">确定删除</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="addVarDialogVisible" title="添加变量开关" width="480px">
      <el-form label-width="80px">
        <el-form-item label="key" required>
          <el-input v-model="newVarForm.key" placeholder="如 NSFW事件" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="newVarForm.label" placeholder="展示名称" />
        </el-form-item>
        <el-form-item label="正文">
          <el-input v-model="newVarForm.body" type="textarea" :rows="6" class="mono-textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addVarDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAddVariable">添加</el-button>
      </template>
    </el-dialog>
</template>

<style scoped>
.test-panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.module-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.variable-edit-area {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
}

.var-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.var-list-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
}

.var-list-title {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.delete-var-dialog-msg {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: #606266;
  white-space: pre-wrap;
  word-break: break-word;
}

.var-list-scroll {
  flex: 1;
  min-height: 120px;
  min-width: 0;
}

.var-list-scroll :deep(.el-scrollbar__wrap) {
  overflow-x: hidden;
}

.var-row {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 8px;
  background: #fafafa;
}

.var-row-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  min-width: 0;
}

.var-label {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.var-row-actions {
  display: flex;
  flex-shrink: 0;
  gap: 2px;
}

.mono-textarea :deep(textarea) {
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 12px;
}

.plain-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
}
</style>
