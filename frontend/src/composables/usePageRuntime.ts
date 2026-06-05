import { computed, ref, watch } from 'vue'
import {
  defaultRuntimeConfig,
  getFirstProfile,
  loadPageRuntime,
  normalizeRuntimeConfig,
  resolveRuntimeRequest,
  savePageRuntime,
  type PageRuntimeConfig,
  type RuntimeScope,
} from '../utils/apiProfileStorage'
import { useApiProfileRegistry } from './useApiProfileRegistry'

export type { RuntimeScope }

const runtimeByScope = new Map<RuntimeScope, ReturnType<typeof createPageRuntime>>()

function createPageRuntime(scope: RuntimeScope) {
  const { registry, getProfileById: getProfile, pickModelForProfile } = useApiProfileRegistry()

  const runtime = ref<PageRuntimeConfig>(loadPageRuntime(scope))

  function persistRuntime() {
    const normalized = normalizeRuntimeConfig(runtime.value, registry.value)
    runtime.value = normalized
    savePageRuntime(scope, normalized)
  }

  function switchProfile(profileId: string) {
    const profile = getProfile(profileId)
    if (!profile) return
    runtime.value.apiProfileId = profile.id
    const kept = (runtime.value.modelNames ?? []).filter((m) => profile.models.includes(m))
    const names =
      kept.length > 0
        ? kept
        : [pickModelForProfile(profile, runtime.value.modelName)].filter(Boolean)
    runtime.value.modelNames = names
    runtime.value.modelName = names[0] ?? pickModelForProfile(profile, '')
    persistRuntime()
  }

  function switchModel(modelName: string) {
    const profile = getProfile(runtime.value.apiProfileId)
    if (!profile || !profile.models.includes(modelName)) return
    runtime.value.modelName = modelName
    runtime.value.modelNames = [modelName]
    persistRuntime()
  }

  function setSelectedModels(modelNames: string[]) {
    const profile = getProfile(runtime.value.apiProfileId)
    if (!profile) return
    const valid = modelNames.filter((m) => profile.models.includes(m))
    runtime.value.modelNames = valid
    runtime.value.modelName = valid[0] ?? ''
    persistRuntime()
  }

  /** 选中当前 API 下按字典序排列的第一个模型 */
  function resetToFirstModelSelection() {
    const profile = getProfile(runtime.value.apiProfileId) ?? getFirstProfile(registry.value)
    if (!profile) return
    const first = [...profile.models].sort((a, b) => a.localeCompare(b))[0]
    if (!first) return
    runtime.value.apiProfileId = profile.id
    setSelectedModels([first])
  }

  function toggleModelSelection(modelName: string, checked: boolean) {
    const profile = getProfile(runtime.value.apiProfileId)
    if (!profile || !profile.models.includes(modelName)) return
    const set = new Set(selectedModelNames.value)
    if (checked) set.add(modelName)
    else set.delete(modelName)
    setSelectedModels([...set])
  }

  function syncWithRegistry() {
    runtime.value = normalizeRuntimeConfig(runtime.value, registry.value)
    persistRuntime()
  }

  const currentProfile = computed(() => getProfile(runtime.value.apiProfileId) ?? null)

  const availableModels = computed(() => {
    const models = currentProfile.value?.models ?? []
    return [...models].sort((a, b) => a.localeCompare(b))
  })

  const selectedModelNames = computed(() => {
    if (Array.isArray(runtime.value.modelNames)) {
      return runtime.value.modelNames
    }
    return runtime.value.modelName ? [runtime.value.modelName] : []
  })

  const hasConfiguredApi = computed(() => {
    if (!currentProfile.value?.base_url.trim() || !currentProfile.value?.api_key.trim()) {
      return false
    }
    return true
  })

  const hasValidRuntime = computed(
    () => hasConfiguredApi.value && selectedModelNames.value.length > 0,
  )

  const resolvedRequest = computed(() => resolveRuntimeRequest(registry.value, runtime.value))

  function resolveRequestWithModelFallback(fallbackModel = '') {
    return resolveRuntimeRequest(registry.value, runtime.value, fallbackModel)
  }

  watch(
    () => runtime.value.temperature,
    () => persistRuntime(),
  )

  watch(
    () => runtime.value.top_k,
    () => persistRuntime(),
  )

  watch(
    registry,
    () => {
      runtime.value = normalizeRuntimeConfig(runtime.value, registry.value)
      persistRuntime()
    },
    { deep: true },
  )

  return {
    scope,
    runtime,
    registry,
    currentProfile,
    availableModels,
    hasValidRuntime,
    hasConfiguredApi,
    resolvedRequest,
    switchProfile,
    switchModel,
    selectedModelNames,
    setSelectedModels,
    resetToFirstModelSelection,
    toggleModelSelection,
    syncWithRegistry,
    persistRuntime,
    resolveRequestWithModelFallback,
    defaultRuntimeConfig,
  }
}

export function usePageRuntime(scope: RuntimeScope) {
  if (!runtimeByScope.has(scope)) {
    runtimeByScope.set(scope, createPageRuntime(scope))
  }
  return runtimeByScope.get(scope)!
}
