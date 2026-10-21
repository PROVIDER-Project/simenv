/** PerformanceObserver sees entries even when removed from the bounded timeline. */
export function measure(name: string, start: number) {
  performance.measure(name, { start, end: performance.now() })
  performance.clearMeasures(name)
}
