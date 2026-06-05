import { computed, ref, watch } from 'vue'
import {
  defaultRuntimeConfig,
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
    const names = runtime.value.modelNames ?? []
    if (names.length > 0) return names
    return runtime.value.modelName ? [runtime.value.modelName] : []
  })

  const hasValidRuntime = computed(() => {
    if (!currentProfile.value?.base_url.trim() || !currentProfile.value?.api_key.trim()) {
      return false
    }
    return selectedModelNames.value.length > 0
  })

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
    resolvedRequest,
    switchProfile,
    switchModel,
    selectedModelNames,
    setSelectedModels,
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
