// Pure helper functions for the Short Selling modal metric cards.
// Extracted from ShortsView.vue so the threshold -> class/hint logic can be
// unit-tested without mounting the Vue component. All inputs are 0-1 scores;
// `undefined` is treated as 0.

export type RiskClass = 'extreme' | 'high' | 'medium' | 'low'

function score(score: number | undefined): number {
  return score ?? 0
}

export function longCrowdClass(c: number | undefined): RiskClass {
  const v = score(c)
  if (v > 0.7) return 'extreme'
  if (v > 0.5) return 'high'
  if (v > 0.3) return 'medium'
  return 'low'
}

export function longCrowdHintText(c: number | undefined): string {
  const v = score(c)
  if (v > 0.7) return '多头极度拥挤,做空胜率↑'
  if (v > 0.4) return '多头仓位偏高,关注'
  if (v > 0.2) return '多空相对平衡'
  return '多头仓位较轻,做空需谨慎'
}

export function extensionClass(e: number | undefined): RiskClass {
  const v = score(e)
  if (v > 0.7) return 'extreme'
  if (v > 0.4) return 'high'
  if (v > 0.2) return 'medium'
  return 'low'
}

export function extensionHintText(e: number | undefined): string {
  const v = score(e)
  if (v > 0.7) return '涨幅已延伸,顶部临近'
  if (v > 0.4) return '涨势明显,可考虑介入'
  if (v > 0.2) return '有一定涨幅'
  return '涨幅未到位,做空风险大'
}
