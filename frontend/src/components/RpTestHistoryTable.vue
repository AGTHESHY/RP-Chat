<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteRpHistoryModels } from '../api'
import type { RpHistoryDetail, RpHistoryModelRun } from '../api'
import { formatHistoryTime } from '../utils/format'

const props = defineProps<{
  detail: RpHistoryDetail | null
  loading?: boolean
  checkedModels: string[]
  compact?: boolean
}>()

const emit = defineEmits<{
  'update:checkedModels': [value: string[]]
  deleted: []
}>()

const modelRuns = computed(() => props.detail?.model_runs ?? [])

function isModelRunEvaluable(run: RpHistoryModelRun): boolean {
  return Boolean(run.compress || run.merge)
}

function isModelRunChecked(run: RpHistoryModelRun): boolean {
  return props.checkedModels.includes(run.model)
}

function modelRunRowClassName({ row }: { row: RpHistoryModelRun }) {
  return isModelRunChecked(row) ? 'rp-test-row--selected' : ''
}

function toggleModelCheck(run: RpHistoryModelRun, checked: boolean) {
  if (!isModelRunEvaluable(run)) return
  const set = new Set(props.checkedModels)
  if (checked) {
    set.add(run.model)
  } else {
    set.delete(run.model)
  }
  emit('update:checkedModels', [...set])
}

function onModelRunRowClick(row: RpHistoryModelRun) {
  if (!isModelRunEvaluable(row)) return
  toggleModelCheck(row, !isModelRunChecked(row))
}

async function removeCheckedRecords() {
  const detail = props.detail
  if (!detail || props.checkedModels.length === 0) return

  const names = props.checkedModels.join('、')
  try {
    await ElMessageBox.confirm(
      `确定删除模型 ${names} 的 RP 测试记录？`,
      '删除 RP 测试历史',
      { type: 'warning' },
    )
    await deleteRpHistoryModels({
      user_id: detail.user_id,
      role_id: detail.role_id,
      app_name: detail.app_name,
      run_group_id: detail.run_group_id,
      models: [...props.checkedModels],
    })
    emit('update:checkedModels', [])
    emit('deleted')
    ElMessage.success('已删除所选模型的 RP 测试记录')
  } catch {
    /* cancelled */
  }
}
</script>

<template>
  <div class="rp-test-history-table">
    <div class="sub-panel-title sub-panel-title-row tab-pane-toolbar">
      <span class="toolbar-hint">勾选模型参与测评对比</span>
      <el-button
        size="small"
        type="danger"
        plain
        :disabled="!detail || checkedModels.length === 0"
        @click="removeCheckedRecords"
      >
        删除
      </el-button>
    </div>
    <p v-if="!detail" class="list-hint tab-pane-hint">请先在上方选择对话</p>
    <div v-else class="rp-model-table-wrap">
      <el-table
        v-loading="loading"
        :data="modelRuns"
        class="eval-table rp-test-table"
        size="small"
        empty-text="暂无测试记录，请先在 RP 测试页运行"
        :row-class-name="modelRunRowClassName"
        @row-click="onModelRunRowClick"
      >
        <el-table-column
          prop="model"
          label="模型"
          :min-width="compact ? 64 : 80"
          show-overflow-tooltip
        />
        <el-table-column
          label="压缩"
          :width="compact ? 40 : 48"
          align="center"
          class-name="col-nowrap"
        >
          <template #default="{ row }">
            {{ row.compress ? '有' : '—' }}
          </template>
        </el-table-column>
        <el-table-column
          label="合并"
          :width="compact ? 40 : 48"
          align="center"
          class-name="col-nowrap"
        >
          <template #default="{ row }">
            {{ row.merge ? '有' : '—' }}
          </template>
        </el-table-column>
        <el-table-column
          label="时间"
          :min-width="compact ? 56 : 68"
          class-name="col-nowrap"
        >
          <template #default="{ row }">
            {{ formatHistoryTime(row.latest_updated_at) }}
          </template>
        </el-table-column>
        <el-table-column
          label="对比"
          :width="compact ? 40 : 44"
          align="center"
          :fixed="compact ? false : 'right'"
        >
          <template #default="{ row }">
            <el-checkbox
              :model-value="isModelRunChecked(row)"
              :disabled="!isModelRunEvaluable(row)"
              @click.stop
              @change="(v: boolean) => toggleModelCheck(row, v)"
            />
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.rp-test-history-table {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.tab-pane-toolbar {
  flex-shrink: 0;
  border-top: none;
  min-height: 36px;
}

.toolbar-hint {
  font-size: 12px;
  color: #909399;
}

.rp-model-table-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: #b1b3b8 transparent;
}

.rp-model-table-wrap::-webkit-scrollbar {
  width: 8px;
}

.rp-model-table-wrap::-webkit-scrollbar-thumb {
  background-color: #b1b3b8;
  border-radius: 4px;
}

.rp-model-table-wrap::-webkit-scrollbar-thumb:hover {
  background-color: #909399;
}

.rp-test-table :deep(.rp-test-row--selected > td) {
  background-color: #ecf5ff !important;
}
</style>
