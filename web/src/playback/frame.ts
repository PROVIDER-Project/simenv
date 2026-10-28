import type { RecordedFrame, Scene } from '../data/playback'
import type { EnvState } from '../data/types'
import { measure } from './measure'

/** Display-only relative stress. Never transforms or replaces recorded measurements. */
export function projectFrame(scene: Pick<Scene, 'edges'>, frame: RecordedFrame, baseline: RecordedFrame) {
  const started = performance.now()
  const reference = new Map(baseline.agents.map(a => [JSON.stringify([a.entity_id, a.agent_id]), a]))
  const markerIntensity: Record<string, number> = {}
  for (const agent of frame.agents) {
    if (agent.role === 'environment') continue
    const first = reference.get(JSON.stringify([agent.entity_id, agent.agent_id]))
    const metric = ['unit_price', 'livestock_output', 'quantity_available'].find(key => typeof agent.values[key] === 'number')
    if (!metric || !first || !first.values[metric]) continue
    const change = (agent.values[metric] - first.values[metric]) / Math.abs(first.values[metric])
    const intensity = Math.max(0, Math.min(1, metric === 'unit_price' ? change : -change))
    markerIntensity[agent.entity_id] = Math.max(markerIntensity[agent.entity_id] ?? 0, intensity)
  }
  const edgeIntensity = Object.fromEntries(scene.edges.map(edge => [edge.id, markerIntensity[edge.source] ?? markerIntensity[edge.target] ?? 0]))
  const values = frame.agents.find(agent => agent.entity_id === 'environment' && agent.agent_id === 0)?.values
  const env: EnvState | null = values ? {
    period: frame.period, soyPrice: values.soy_price, feedPrice: values.feed_price,
    shockScale: values.shock_scale, droughtSeverity: values.drought_severity,
    totalSoySupply: values.total_soy_supply, transportUtilisation: values.transport_utilisation,
    currentStep: values.current_step,
  } : null
  measure('playback.project', started)
  return { markerIntensity, edgeIntensity, env }
}
