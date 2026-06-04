<script setup lang="ts">
defineProps<{
  turns: { question: string; answer: string }[]
}>()
</script>

<template>
  <div class="chat-qa-thread">
    <div v-for="(turn, index) in turns" :key="index" class="chat-qa-bubble">
      <div class="bubble-row answer-row">
        <div class="bubble answer-bubble">
          <div class="bubble-label">答</div>
          <div class="bubble-text">{{ turn.answer || '（无回复）' }}</div>
        </div>
      </div>
      <div class="bubble-row question-row">
        <div class="bubble question-bubble">
          <div class="bubble-label">问</div>
          <div class="bubble-text">{{ turn.question || '（无问题）' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-qa-thread {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.chat-qa-bubble {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 8px 4px;
}

.bubble-row {
  display: flex;
  width: 100%;
}

.answer-row {
  justify-content: flex-start;
}

.question-row {
  justify-content: flex-end;
}

.bubble {
  max-width: 82%;
  padding: 12px 14px;
  border-radius: 12px;
  line-height: 1.6;
  font-size: 14px;
  white-space: pre-wrap;
  word-break: break-word;
}

.answer-bubble {
  background: #f4f4f5;
  border: 1px solid #ebeef5;
  border-top-left-radius: 4px;
}

.question-bubble {
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  border-top-right-radius: 4px;
}

.bubble-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
  font-weight: 600;
}

.bubble-text {
  color: #303133;
}
</style>
