import { ref, type Ref } from 'vue'

export function useSelectableList<T, K extends string | number>(
  getKey: (item: T) => K,
) {
  const selectedKey = ref<K | null>(null) as Ref<K | null>

  function syncSelection(list: T[], keepCurrent = true): void {
    if (list.length === 0) {
      selectedKey.value = null
      return
    }
    if (keepCurrent && selectedKey.value !== null) {
      const exists = list.some((item) => getKey(item) === selectedKey.value)
      if (exists) return
    }
    selectedKey.value = getKey(list[0])
  }

  function selectByKey(key: K | null): void {
    selectedKey.value = key
  }

  return { selectedKey, syncSelection, selectByKey }
}
