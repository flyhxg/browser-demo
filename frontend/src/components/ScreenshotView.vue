<template>
  <div class="screenshot-view">
    <h3>Browser View</h3>
    <div v-if="screenshot" class="screenshot-container">
      <img :src="'data:image/png;base64,' + screenshot" alt="Browser screenshot" />
    </div>
    <div v-else class="empty">No screenshot yet</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ screenshot: string | null }>()
</script>

<style scoped>
.screenshot-view {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 12px;
}
h3 { margin: 0 0 8px; }
.screenshot-container {
  overflow: hidden;
  border-radius: 4px;
  border: 1px solid #eee;
}
img {
  width: 100%;
  height: auto;
  display: block;
}
.empty { color: #999; font-style: italic; text-align: center; padding: 40px; }
</style>
