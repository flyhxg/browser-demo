<template>
  <div class="comparison-chart">
    <h3>Token Comparison</h3>
    <table v-if="tokens.length">
      <thead>
        <tr><th>Token</th><th>Confidence</th><th>Recommendation</th></tr>
      </thead>
      <tbody>
        <tr v-for="token in tokens" :key="token.symbol">
          <td>{{ token.symbol }}</td>
          <td>{{ token.llm_analysis?.confidence ?? '-' }}</td>
          <td>{{ token.llm_analysis?.recommendation ?? '-' }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else>No comparison data.</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{ tokens: any[] }>()
</script>

<style scoped>
.comparison-chart table { width: 100%; border-collapse: collapse; }
.comparison-chart th, .comparison-chart td { border: 1px solid #ddd; padding: 8px; text-align: left; }
</style>
