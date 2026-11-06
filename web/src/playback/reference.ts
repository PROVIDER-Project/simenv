import type { AgentState, Scene } from '../data/playback'

export interface RecordedReference {
  runId: string
  scenarioId: number
  evidence: 'scenario-zero' | 'empty-events'
}
export type ReferenceChoice = string | RecordedReference | null
export function recordedReference(choice: string | RecordedReference): RecordedReference {
  return typeof choice === 'string' ? { runId: choice, scenarioId: 0, evidence: 'scenario-zero' } : choice
}

export const agentIdentity = (agent: Pick<AgentState, 'entity_id' | 'agent_id' | 'role'>) =>
  JSON.stringify([agent.entity_id, agent.agent_id, agent.role])

/** Compare structure, never cosmetic labels, geography, order or filenames. */
export function referenceCompatibility(current: Scene, reference: Scene, evidence: RecordedReference['evidence'] = 'scenario-zero'): string | null {
  if (reference.scenario_id !== 0 && evidence !== 'empty-events') return 'An unshocked reference must be recorded scenario 0 or have verified empty events'
  if (reference.min_period > current.min_period || reference.max_period < current.max_period) return 'Reference does not cover the selected period range'
  const signature = (scene: Scene) => JSON.stringify({
    nodes: scene.nodes.map(node => [node.id, node.role, [...node.entityIds].sort(), node.hasRecordedData]).sort(),
    edges: scene.edges.map(edge => [edge.id, edge.source, edge.target, edge.isSeaCrossing]).sort(),
  })
  return signature(current) === signature(reference) ? null : 'Reference network structure is incompatible'
}
