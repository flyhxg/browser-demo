<template>
  <div class="chat-history" ref="listEl">
    <div
      v-for="(msg, idx) in messages"
      :key="idx"
    >
      <ChatMessage :message="msg" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import ChatMessage from './ChatMessage.vue'
import type { ChatMessage as ChatMessageData } from '../types'

const props = defineProps<{ messages: ChatMessageData[] }>()
const listEl = ref<HTMLElement | null>(null)

watch(() => props.messages.length, async () => {
  await nextTick()
  if (listEl.value) {
    listEl.value.scrollTop = listEl.value.scrollHeight
  }
})
</script>

<style scoped>
.chat-history {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
}
</style>