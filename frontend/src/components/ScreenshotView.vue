<template>
  <div class="screenshot-view">
    <h3>Browser View</h3>
    <div v-if="liveUrl" class="live-url-section">
      <div class="live-url-label">Live Browser URL:</div>
      <a :href="liveUrl" target="_blank" rel="noopener noreferrer" class="live-url-link">{{ liveUrl }}</a>
      <div class="live-url-hint">Click to open in new tab</div>
    </div>
    <div v-if="liveUrl" class="screenshot-container">
      <iframe :src="liveUrl" allow="fullscreen" />
    </div>
    <div v-else-if="screenshot" class="screenshot-container">
      <img :src="'data:image/png;base64,' + screenshot" alt="Browser screenshot" />
    </div>
    <div v-else class="empty">No screenshot yet</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ screenshot: string | null; liveUrl?: string | null }>()
</script>

<style scoped>
.screenshot-view {
  background: #18181b;
  border: 1px solid #27272a;
  border-radius: 10px;
  padding: 16px;
}
h3 { margin: 0 0 12px; font-size: 14px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.5px; }
.live-url-section {
  margin-bottom: 12px;
  padding: 10px;
  background: #1f1f23;
  border-radius: 6px;
  border: 1px solid #27272a;
}
.live-url-label {
  font-size: 12px;
  color: #a1a1aa;
  margin-bottom: 6px;
}
.live-url-link {
  display: block;
  font-size: 13px;
  color: #6366f1;
  word-break: break-all;
  text-decoration: none;
  margin-bottom: 4px;
}
.live-url-link:hover {
  text-decoration: underline;
}
.live-url-hint {
  font-size: 11px;
  color: #52525b;
}
.screenshot-container {
  overflow: hidden;
  border-radius: 6px;
  border: 1px solid #27272a;
  background: #000;
}
img { width: 100%; height: auto; display: block; }
iframe {
  width: 100%;
  height: 500px;
  border: none;
  border-radius: 6px;
  background: #000;
}
.empty { color: #52525b; font-style: italic; text-align: center; padding: 48px; }
</style>
