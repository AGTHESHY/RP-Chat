<script setup lang="ts">
import JsonVisualValue from './JsonVisualValue.vue'

const props = defineProps<{
  value: unknown
  depth: number
  keyName?: string
  isLast?: boolean
}>()

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function formatPrimitive(value: unknown): string {
  if (value === null) return 'null'
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

const isObject = isPlainObject(props.value)
const isArray = Array.isArray(props.value)
const isPrimitive = !isObject && !isArray

const objectEntries = isObject ? Object.entries(props.value) : []
const arrayItems = isArray ? props.value : []
</script>

<template>
  <div class="json-node">
    <div v-if="keyName !== undefined" class="json-line" :style="{ paddingLeft: `${depth * 18}px` }">
      <span class="json-key">"{{ keyName }}"</span><span class="json-punct">: </span>
      <template v-if="isPrimitive">
        <span class="json-value">{{ formatPrimitive(value) }}</span><span class="json-punct">{{ isLast ? '' : ',' }}</span>
      </template>
      <span v-else-if="isArray" class="json-punct">[</span>
      <span v-else class="json-punct">{</span>
    </div>

    <template v-if="isArray && keyName === undefined && depth === 0">
      <span class="json-punct">[</span>
    </template>
    <template v-if="isObject && keyName === undefined && depth === 0">
      <span class="json-punct">{</span>
    </template>

    <template v-if="isArray">
      <template v-for="(item, index) in arrayItems" :key="index">
        <JsonVisualValue
          v-if="typeof item === 'object' && item !== null"
          :value="item"
          :depth="depth + 1"
          :is-last="index === arrayItems.length - 1"
        />
        <div
          v-else
          class="json-line"
          :style="{ paddingLeft: `${(depth + 1) * 18}px` }"
        >
          <span class="json-value">{{ formatPrimitive(item) }}</span><span class="json-punct">{{ index === arrayItems.length - 1 ? '' : ',' }}</span>
        </div>
      </template>
      <div
        v-if="arrayItems.length === 0"
        class="json-line json-empty"
        :style="{ paddingLeft: `${(depth + 1) * 18}px` }"
      />
      <div class="json-line" :style="{ paddingLeft: `${depth * 18}px` }">
        <span class="json-punct">]</span><span v-if="keyName !== undefined" class="json-punct">{{ isLast ? '' : ',' }}</span>
      </div>
    </template>

    <template v-else-if="isObject">
      <JsonVisualValue
        v-for="([childKey, childValue], index) in objectEntries"
        :key="childKey"
        :value="childValue"
        :depth="depth + 1"
        :key-name="childKey"
        :is-last="index === objectEntries.length - 1"
      />
      <div
        v-if="objectEntries.length === 0"
        class="json-line json-empty"
        :style="{ paddingLeft: `${(depth + 1) * 18}px` }"
      />
      <div class="json-line" :style="{ paddingLeft: `${depth * 18}px` }">
        <span class="json-punct">}</span><span v-if="keyName !== undefined" class="json-punct">{{ isLast ? '' : ',' }}</span>
      </div>
    </template>

    <div
      v-else-if="isPrimitive && keyName === undefined"
      class="json-line"
      :style="{ paddingLeft: `${depth * 18}px` }"
    >
      <span class="json-value">{{ formatPrimitive(value) }}</span>
    </div>
  </div>
</template>

<style scoped>
.json-key {
  font-weight: 700;
  color: #1a1a1a;
}

.json-value {
  color: #c4a035;
  background: #fff9e6;
  padding: 0 3px;
  border-radius: 3px;
}

.json-punct {
  color: #606266;
}

.json-line {
  white-space: pre-wrap;
}

.json-empty {
  min-height: 0;
}
</style>
