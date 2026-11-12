import type { Scene } from '../data/playback'
import type { Node } from '../data/types'
import { aggregateAssessments, unavailable, type Assessment, type NodeAssessment } from './status'

type ConnectionScene = Pick<Scene, 'edges'> & Partial<Pick<Scene, 'nodes'>>

export interface ConnectionSource {
  nodeId: string
  /** Upstream component followed by the unrecorded transports towards the edge. */
  path: string[]
  assessment: NodeAssessment
}

export interface ConnectionAssessment extends Assessment {
  kind: 'source' | 'inferred'
  sources: ConnectionSource[]
  unresolved: { path: string[]; reason: string }[]
  winner: ({ nodeId: string } & NonNullable<NodeAssessment['winner']>) | null
}

// `port` is the explicit legacy port role also used by older scene fixtures.
const transportRoles = new Set(['land_transport', 'sea_transport', 'port'])
const unrecordedTransport = (node: Node) => node.hasRecordedData === false && transportRoles.has(node.role)
const missing = (reason: string): NodeAssessment => ({ ...unavailable(reason), agents: [], winner: null })

/** Resolve display evidence only. Missing recorded evidence is never bypassed. */
export function resolveConnections(scene: ConnectionScene, assessments: Record<string, NodeAssessment>): Record<string, ConnectionAssessment> {
  const nodes = new Map(scene.nodes?.map(node => [node.id, node]))
  const incoming = new Map<string, Set<string>>()
  for (const edge of scene.edges) {
    const sources = incoming.get(edge.target) ?? new Set<string>()
    sources.add(edge.source)
    incoming.set(edge.target, sources)
  }

  function resolve(sourceId: string, destinationId: string): ConnectionAssessment {
    const sources: ConnectionSource[] = []
    const unresolved: ConnectionAssessment['unresolved'] = []
    const sourceNode = nodes.get(sourceId)
    const inferred = sourceNode ? unrecordedTransport(sourceNode) : false

    function visit(id: string, downstream: string[]) {
      const path = [id, ...downstream]
      const node = nodes.get(id)
      if (inferred && id === destinationId) {
        unresolved.push({ path, reason: 'Upstream path reaches this connection’s destination' })
      } else if (downstream.includes(id)) {
        unresolved.push({ path, reason: 'Cycle in upstream transport path' })
      } else if (scene.nodes && !node) {
        unresolved.push({ path, reason: 'Upstream component is absent from the scene' })
      } else if (node && unrecordedTransport(node)) {
        const upstream = [...(incoming.get(id) ?? [])].sort()
        if (!upstream.length) unresolved.push({ path, reason: 'Unrecorded transport has no upstream component' })
        for (const parent of upstream) visit(parent, path)
      } else {
        // Unknown metadata is never a license to traverse; metadata-free callers
        // retain the original immediate-source behavior.
        const assessment = assessments[id] ?? missing('Upstream status unavailable')
        sources.push({ nodeId: id, path, assessment })
      }
    }

    visit(sourceId, [])
    const overall = !inferred && sources.length === 1
      ? sources[0].assessment
      : aggregateAssessments([...sources.map(source => source.assessment), ...unresolved.map(item => unavailable(item.reason))])
    const strongest = sources.filter(source => source.assessment.score !== null)
      .reduce<ConnectionSource | null>((best, source) => !best || source.assessment.score! > best.assessment.score! ? source : best, null)
    const winner = overall.score !== null && strongest?.assessment.winner
      ? { nodeId: strongest.nodeId, ...strongest.assessment.winner } : null
    return { ...overall, kind: inferred ? 'inferred' : 'source', sources, unresolved, winner }
  }

  // Destination exclusions make inference edge-specific, even for shared sources.
  return Object.fromEntries(scene.edges.map(edge => [edge.id, resolve(edge.source, edge.target)]))
}
