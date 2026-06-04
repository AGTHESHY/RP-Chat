import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { normalizeBaseUrl } from '../utils/apiConfigStorage'
import {
  clearApiProfileRegistry,
  createDefaultProfile,
  getFirstProfile,
  getProfileById,
  hasSavedApiProfileRegistry,
  loadApiProfileRegistry,
  pickModelForProfile,
  saveApiProfileRegistry,
  type ApiProfile,
  type ApiProfileRegistry,
} from '../utils/apiProfileStorage'

const registry = ref<ApiProfileRegistry>(loadApiProfileRegistry())
const configLoadedFromStorage = ref(hasSavedApiProfileRegistry())
const lastSavedAt = ref<Date | null>(configLoadedFromStorage.value ? new Date() : null)

let saveTimer: ReturnType<typeof setTimeout> | null = null
let skipAutoSave = false
let watchInitialized = false

function flushRegistrySave() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  if (skipAutoSave) return
  saveApiProfileRegistry(registry.value)
  lastSavedAt.value = new Date()
  configLoadedFromStorage.value = true
}

function scheduleAutoSave() {
  if (skipAutoSave) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    flushRegistrySave()
  }, 400)
}

function initRegistryWatch() {
  if (watchInitialized) return
  watchInitialized = true
  watch(
    registry,
    () => {
      scheduleAutoSave()
    },
    { deep: true },
  )
}

export function formatApiDisplayUrl(url: string): string {
  const normalized = normalizeBaseUrl(url.trim())
  if (!normalized) return '未设置'
  try {
    const parsed = new URL(normalized)
    const path = parsed.pathname.replace(/\/v1\/chat\/completions\/?$/, '')
    return `${parsed.host}${path || ''}`
  } catch {
    return normalized.length > 40 ? `${normalized.slice(0, 40)}…` : normalized
  }
}

export function useApiProfileRegistry() {
  initRegistryWatch()

  function reloadRegistry() {
    flushRegistrySave()
    registry.value = loadApiProfileRegistry()
    configLoadedFromStorage.value = hasSavedApiProfileRegistry()
  }

  function formatSavedTime(date: Date | null): string {
    if (!date) return ''
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  function clearAllProfiles() {
    skipAutoSave = true
    clearApiProfileRegistry()
    registry.value = { profiles: [createDefaultProfile()] }
    saveApiProfileRegistry(registry.value)
    configLoadedFromStorage.value = false
    lastSavedAt.value = null
    ElMessage.success('已清除全部 API 配置')
    setTimeout(() => {
      skipAutoSave = false
    }, 500)
  }

  function addProfile(): ApiProfile {
    const profile = createDefaultProfile({
      name: `API ${registry.value.profiles.length + 1}`,
    })
    registry.value.profiles.push(profile)
    return profile
  }

  function removeProfile(id: string) {
    if (registry.value.profiles.length <= 1) {
      ElMessage.warning('至少保留一个 API 配置')
      return
    }
    registry.value.profiles = registry.value.profiles.filter((item) => item.id !== id)
  }

  function normalizeProfileBaseUrl(profile: ApiProfile) {
    const normalized = normalizeBaseUrl(profile.base_url)
    if (normalized !== profile.base_url.trim()) {
      profile.base_url = normalized
    }
  }

  function addModelToProfile(profileId: string, modelName: string): boolean {
    const name = modelName.trim()
    if (!name) return false
    const profile = getProfileById(registry.value, profileId)
    if (!profile) return false
    if (profile.models.includes(name)) {
      ElMessage.warning('该 model 已存在')
      return false
    }
    profile.models.push(name)
    flushRegistrySave()
    return true
  }

  function removeModelFromProfile(profileId: string, modelName: string): boolean {
    const profile = getProfileById(registry.value, profileId)
    if (!profile) return false
    if (profile.models.length <= 1) {
      ElMessage.warning('至少保留一个 model')
      return false
    }
    profile.models = profile.models.filter((item) => item !== modelName)
    flushRegistrySave()
    return true
  }

  return {
    registry,
    configLoadedFromStorage,
    lastSavedAt,
    flushRegistrySave,
    reloadRegistry,
    formatSavedTime,
    clearAllProfiles,
    addProfile,
    removeProfile,
    normalizeProfileBaseUrl,
    addModelToProfile,
    removeModelFromProfile,
    getProfileById: (id: string) => getProfileById(registry.value, id),
    getFirstProfile: () => getFirstProfile(registry.value),
    pickModelForProfile,
  }
}
