import type { AgentState } from '../data/playback'

/** Illustrative workshop policy; independent of run ranges and cached pages. */
export const thresholds = { relative: [0.05, 0.2, 0.5], capacity: [0.8, 0.95] } as const
type Direction = 'increase' | 'decrease' | 'capacity' | 'participation' | 'diagnostic'
interface MetricDefinition { key: string; label: string; direction: Direction; optional?: boolean }
export interface MetricStatus extends MetricDefinition {
  current: number | null
  reference: number | null
  change: number | null
  score: number | null
  reason: string
}
export interface Assessment {
  score: number | null
  coverage: 'complete' | 'partial' | 'unavailable'
  reason: string
  metrics: MetricStatus[]
}
export interface AgentAssessment extends Assessment { agent: Pick<AgentState, 'entity_id' | 'agent_id' | 'role'> }
export interface NodeAssessment extends Assessment {
  agents: AgentAssessment[]
  winner: { agent: AgentAssessment['agent']; metric: MetricStatus } | null
}

const price: MetricDefinition = { key: 'unit_price', label: 'Asking price', direction: 'increase' }
const quantity: MetricDefinition = { key: 'quantity_available', label: 'Supply availability', direction: 'decrease' }
const active: MetricDefinition = { key: 'active', label: 'Market participation', direction: 'participation', optional: true }
const inputs: MetricDefinition[] = [
  { key: 'input_received', label: 'Input offered', direction: 'decrease', optional: true },
  { key: 'input_processed', label: 'Input processed', direction: 'decrease', optional: true },
  { key: 'unused_input', label: 'Unused input (diagnostic)', direction: 'diagnostic', optional: true },
]
const registry: Record<string, MetricDefinition[]> = {
  producer: [price, quantity, active],
  wholesaler: [price, quantity, { key: 'storage_utilization', label: 'Storage/handling pressure', direction: 'capacity' }],
  processor: [price, quantity, ...inputs],
  feed_manufacturer: [price, quantity, ...inputs],
  feed_trader: [price, quantity],
  consumer: [
    { key: 'feed_received', label: 'Feed availability', direction: 'decrease' },
    { key: 'livestock_output', label: 'Livestock output', direction: 'decrease' }, active,
  ],
  environment: [
    { key: 'soy_price', label: 'Soy price', direction: 'increase' },
    { key: 'feed_price', label: 'Feed price', direction: 'increase' },
    { key: 'total_soy_supply', label: 'Total soy supply', direction: 'decrease' },
    { key: 'transport_utilisation', label: 'Average transport utilization', direction: 'capacity' },
  ],
}
const finite = (value: number | undefined): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null
const percent = (value: number) => `${(value * 100).toFixed(1).replace(/\.0$/, '')}%`

function relativeScore(change: number): number {
  const [green, amber, red] = thresholds.relative
  if (change <= green) return 0
  if (change < amber) return .5 * (change - green) / (amber - green)
  return Math.min(1, .5 + .5 * (change - amber) / (red - amber))
}

function evaluateMetric(def: MetricDefinition, current: AgentState, reference?: AgentState): MetricStatus {
  const value = finite(current.values[def.key])
  const base = finite(reference?.values[def.key])
  const result: MetricStatus = { ...def, current: value, reference: base, change: null, score: null, reason: '' }
  if (value === null) return { ...result, reason: `${def.label}: current measurement unavailable` }
  if (def.direction === 'diagnostic') return { ...result, reason: 'Diagnostic only; not evidence of production utilization or unmet demand' }
  if (def.direction === 'participation') {
    return { ...result, score: value === 0 ? 1 : value === 1 ? 0 : null,
      reason: value === 0 ? 'Market participation: inactive' : value === 1 ? 'Market participation: active' : 'Invalid participation flag' }
  }
  if (value < 0) return { ...result, reason: `${def.label}: invalid negative measurement` }
  if (def.direction === 'capacity') {
    const [amber, red] = thresholds.capacity
    return { ...result, score: value < amber ? 0 : Math.min(1, .5 + .5 * (value - amber) / (red - amber)), reason: `${def.label} ${percent(value)}` }
  }
  if (def.direction === 'increase' && value === 0) return { ...result, reason: `${def.label}: no quote / no contributing volume` }
  if (base === null || base <= 0) return { ...result, reason: `${def.label}: positive reference unavailable` }
  const change = (value - base) / base
  return { ...result, change, score: relativeScore(def.direction === 'increase' ? change : -change),
    reason: `${def.label} ${change < 0 ? 'down' : 'up'} ${percent(Math.abs(change))}` }
}

export function unavailable(reason: string): Assessment {
  return { score: null, coverage: 'unavailable', reason, metrics: [] }
}

export function aggregateAssessments(items: Assessment[]): Assessment {
  const scored = items.filter(item => item.score !== null)
  if (!scored.length) return { ...unavailable(items[0]?.reason ?? 'No applicable recorded measurements'),
    coverage: items.some(item => item.coverage === 'partial') ? 'partial' : 'unavailable' }
  const winner = scored.reduce((a, b) => b.score! > a.score! ? b : a)
  const complete = items.every(item => item.coverage === 'complete')
  const score = !complete && winner.score === 0 ? null : winner.score
  return { score, coverage: complete ? 'complete' : 'partial', metrics: [],
    reason: score === null ? 'Insufficient evidence to call this component healthy' : winner.reason }
}

export function evaluateAgent(current: AgentState, reference?: AgentState, expected?: AgentState): Assessment {
  // Callers match exact entity/agent/role identities before passing references.
  const definitions = (registry[current.role] ?? []).filter(def => !def.optional ||
    def.key in current.values || (reference && def.key in reference.values) || (expected && def.key in expected.values))
  const metrics = definitions.map(def => evaluateMetric(def, current, reference))
  const assessed = metrics.filter(metric => metric.direction !== 'diagnostic').map(metric => ({
    score: metric.score, coverage: metric.score === null ? 'unavailable' as const : 'complete' as const,
    reason: metric.reason, metrics: [metric],
  }))
  return { ...aggregateAssessments(assessed), metrics }
}

export function assessNode(agents: AgentAssessment[]): NodeAssessment {
  const overall = aggregateAssessments(agents)
  let winner: NodeAssessment['winner'] = null
  for (const agent of agents) {
    for (const metric of agent.metrics) {
      if (metric.score !== null && (!winner || metric.score > winner.metric.score!)) winner = { agent: agent.agent, metric }
    }
  }
  return { ...overall, agents, winner }
}
