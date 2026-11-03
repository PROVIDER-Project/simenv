import type { RecordedFrame, Scene } from '../data/playback'
import type { EnvState } from '../data/types'
import { measure } from './measure'
import { agentIdentity } from './reference'
import { assessNode, evaluateAgent, unavailable, type AgentAssessment, type NodeAssessment } from './status'

/** Display-only relative stress. Never transforms or replaces recorded measurements. */
export function projectFrame(scene: Pick<Scene, 'edges'> & Partial<Pick<Scene, 'nodes'>>, frame: RecordedFrame, baseline: RecordedFrame | null, expected?: RecordedFrame | null) {
  const started = performance.now()
  const reference = new Map(baseline?.agents.map(a => [agentIdentity(a), a]))
  const census = new Map(expected?.agents.map(a => [agentIdentity(a), a]))
  const current = new Map(frame.agents.map(a => [agentIdentity(a), a]))
  const groups = new Map<string, AgentAssessment[]>()
  const identities = [...new Set([...current.keys(), ...census.keys(), ...reference.keys()])].sort()
  for (const id of identities) {
    const agent = current.get(id)
    const identity = agent ?? census.get(id) ?? reference.get(id)!
    const assessment = agent ? evaluateAgent(agent, reference.get(id), census.get(id)) : unavailable('Expected agent is missing from this recorded period')
    const list = groups.get(identity.entity_id) ?? []
    list.push({ ...assessment, agent: { entity_id: identity.entity_id, agent_id: identity.agent_id, role: identity.role } })
    groups.set(identity.entity_id, list)
  }
  const nodes: Record<string, NodeAssessment> = Object.fromEntries([...groups].filter(([id]) => id !== 'environment').map(([id, agents]) => [id, assessNode(agents)]))
  for (const node of scene.nodes ?? []) {
    if (!nodes[node.id] || !node.hasRecordedData) nodes[node.id] = { ...unavailable('No measurements recorded for this component'), agents: [], winner: null }
  }
  const edges = Object.fromEntries(scene.edges.map(edge => [edge.id, nodes[edge.source] ?? { ...unavailable('Upstream status unavailable'), agents: [], winner: null }]))
  const markerIntensity = Object.fromEntries(Object.entries(nodes).map(([id, status]) => [id, status.score]))
  const edgeIntensity = Object.fromEntries(Object.entries(edges).map(([id, status]) => [id, status.score]))
  const environment = { entity_id: 'environment', agent_id: 0, role: 'environment', values: {} }
  const indicators = evaluateAgent(current.get(agentIdentity(environment)) ?? environment,
    reference.get(agentIdentity(environment))).metrics
  const values = frame.agents.find(agent => agent.entity_id === 'environment' && agent.agent_id === 0)?.values
  const env: EnvState | null = values ? {
    period: frame.period, soyPrice: values.soy_price, feedPrice: values.feed_price,
    shockScale: values.shock_scale, droughtSeverity: values.drought_severity,
    totalSoySupply: values.total_soy_supply, transportUtilisation: values.transport_utilisation,
    currentStep: values.current_step,
  } : null
  measure('playback.project', started)
  return { nodes, edges, indicators, markerIntensity, edgeIntensity, env }
}
