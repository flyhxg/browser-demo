<template>
  <div class="message" :class="message.role">
    <div class="bubble">
      <p class="text">{{ message.text }}</p>
      <span class="time">{{ formattedTime }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChatMessage } from '../types'

const props = defineProps<{ message: ChatMessage }>()

const formattedTime = computed(() => {
  return props.message.timestamp.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
})
</script>

<style scoped>
.message {
  display: flex;
  margin-bottom: 16px;
}
.message.user {
  justify-content: flex-end;
}
.message.assistant {
  justify-content: flex-start;
}
.bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 12px;
  position: relative;
}
.message.user .bubble {
  background: #6366F1;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.message.assistant .bubble {
  background: #2D2D2F;
  color: #E4E4E7;
  border-bottom-left-radius: 4px;
}
.text {
  margin: 0;
  white-space: pre-wrap;
  font-size: 14px;
  line-height: 1.5;
}
.time {
  display: block;
  font-size: 11px;
  margin-top: 4px;
  opacity: 0.6;
}
.message.user .time { text-align: right; }
</style>