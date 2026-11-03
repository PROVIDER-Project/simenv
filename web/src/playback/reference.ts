import type { AgentState, Scene } from '../data/playback'

export const agentIdentity = (agent: Pick<AgentState, 'entity_id' | 'agent_id' | 'role'>) =>
  JSON.stringify([agent.entity_id, agent.agent_id, agent.role])

/** Compare structure, never cosmetic labels, geography, order or filenames. */
export function referenceCompatibility(current: Scene, reference: Scene): string | null {
  if (reference.scenario_id !== 0) return 'An unshocked reference must be recorded scenario 0'
  if (reference.min_period > current.min_period || reference.max_period < current.max_period) return 'Reference does not cover the selected period range'
  const signature = (scene: Scene) => JSON.stringify({
    nodes: scene.nodes.map(node => [node.id, node.role, [...node.entityIds].sort(), node.hasRecordedData]).sort(),
    edges: scene.edges.map(edge => [edge.id, edge.source, edge.target, edge.isSeaCrossing]).sort(),
  })
  return signature(current) === signature(reference) ? null : 'Reference network structure is incompatible'
}
