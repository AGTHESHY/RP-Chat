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
    runtime.value.modelName = pickModelForProfile(profile, runtime.value.modelName)
    persistRuntime()
  }

  function switchModel(modelName: string) {
    const profile = getProfile(runtime.value.apiProfileId)
    if (!profile || !profile.models.includes(modelName)) return
    runtime.value.modelName = modelName
    persistRuntime()
  }

  function syncWithRegistry() {
    runtime.value = normalizeRuntimeConfig(runtime.value, registry.value)
    persistRuntime()
  }

  const currentProfile = computed(() => getProfile(runtime.value.apiProfileId) ?? null)

  const availableModels = computed(() => currentProfile.value?.models ?? [])

  const hasValidRuntime = computed(() =>
    Boolean(resolveRuntimeRequest(registry.value, runtime.value)),
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
    resolvedRequest,
    switchProfile,
    switchModel,
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
