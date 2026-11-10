import { statusPalette } from './tokens'

/** Shared traffic-light gradient; null is deliberately distinct from zero. */
export function statusColor(score: number | null): string {
  if (score === null) return statusPalette.unavailable
  const [a, b, t] = score <= .5
    ? [statusPalette.green, statusPalette.amber, score * 2]
    : [statusPalette.amber, statusPalette.red, (score - .5) * 2]
  const rgb = (hex: string) => [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16))
  const start = rgb(a), end = rgb(b)
  return `#${start.map((value, index) => Math.round(value + (end[index] - value) * t).toString(16).padStart(2, '0')).join('')}`
}

export function statusLabel(score: number | null): string {
  return score === null ? 'Unavailable' : score === 0 ? 'Near reference / low pressure' : score < .5 ? 'Increasing adverse change' : score < 1 ? 'Elevated' : 'Severe'
}

export function formatValue(value: number | null, capacity = false): string {
  return value === null ? 'Unavailable' : capacity ? `${(value * 100).toFixed(1)}%` : new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 }).format(value)
}
