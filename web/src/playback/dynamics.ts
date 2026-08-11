/**
 * Playback dynamics — turns a bundle's recorded ticks into a per-period "frame"
 * the globe can render.
 *
 * Each recorded node gets a stress scalar per period (a rising price, or a
 * falling output/quantity, reads as more disruption), normalised over the run to
 * a 0..1 intensity. A corridor carries its source node's intensity downstream.
 * Ports and any flat series contribute no intensity. This mirrors the reference
 * explorer's cascade ramp, driven here by the actual simulation output.
 */

import type { Bundle, EnvState } from '../data/types'

export interface Frame {
  /** nodeId -> 0..1 intensity for this period. */
  markerIntensity: Record<string, number>
  /** edgeId -> 0..1 intensity for this period. */
  edgeIntensity: Record<string, number>
}

export interface Dynamics {
  /** Sorted list of periods available for playback. */
  periods: number[]
  frameAt(period: number): Frame
  envAt(period: number): EnvState | null
}

/** A single "badness" scalar per tick: higher means more disruption. */
function stressOf(values: Record<string, number | boolean | null>): number | null {
  if (typeof values.unit_price === 'number') return values.unit_price
  if (typeof values.livestock_output === 'number') return -values.livestock_output
  if (typeof values.quantity_available === 'number') return -values.quantity_available
  return null
}

const EMPTY_FRAME: Frame = { markerIntensity: {}, edgeIntensity: {} }

export function buildDynamics(bundle: Bundle): Dynamics {
  const byNode = new Map<string, Map<number, number>>()
  for (const tick of bundle.ticks) {
    const stress = stressOf(tick.values)
    if (stress === null) continue
    let series = byNode.get(tick.nodeId)
    if (!series) {
      series = new Map<number, number>()
      byNode.set(tick.nodeId, series)
    }
    series.set(tick.period, stress)
  }

  const range = new Map<string, { min: number; max: number }>()
  for (const [nodeId, series] of byNode) {
    let min = Infinity
    let max = -Infinity
    for (const value of series.values()) {
      if (value < min) min = value
      if (value > max) max = value
    }
    range.set(nodeId, { min, max })
  }

  const nodeIntensity = (nodeId: string, period: number): number => {
    const series = byNode.get(nodeId)
    const bounds = range.get(nodeId)
    if (!series || !bounds) return 0
    const value = series.get(period)
    if (value === undefined || bounds.max === bounds.min) return 0
    return (value - bounds.min) / (bounds.max - bounds.min)
  }

  const periods = bundle.env.map((snapshot) => snapshot.period).sort((a, b) => a - b)
  const envByPeriod = new Map(bundle.env.map((snapshot) => [snapshot.period, snapshot]))
  const frameCache = new Map<number, Frame>()

  return {
    periods,
    frameAt(period: number): Frame {
      const cached = frameCache.get(period)
      if (cached) return cached
      const markerIntensity: Record<string, number> = {}
      for (const nodeId of byNode.keys()) markerIntensity[nodeId] = nodeIntensity(nodeId, period)
      const edgeIntensity: Record<string, number> = {}
      for (const edge of bundle.edges) {
        edgeIntensity[edge.id] = markerIntensity[edge.source] ?? markerIntensity[edge.target] ?? 0
      }
      const frame: Frame = { markerIntensity, edgeIntensity }
      frameCache.set(period, frame)
      return frame
    },
    envAt(period: number): EnvState | null {
      return envByPeriod.get(period) ?? null
    },
  }
}

export { EMPTY_FRAME }
