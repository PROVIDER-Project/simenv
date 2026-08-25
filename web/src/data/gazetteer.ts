/**
 * Gazetteer — fallback coordinates for entities without declared placements.
 *
 * PDL/roster coordinates reach the frontend on bundle nodes and take precedence.
 * Fallbacks live HERE, keyed by PDL entity id. Their lat/lon values are ported
 * from branch 21's `visualization/config/layout.py` (`GROUP_ANCHORS`, `PORTS`) —
 * projection-independent, so they carry to the globe unchanged. The
 * equirectangular `project()` from that file is dead on a globe and not ported.
 *
 * This is explicitly "approximate geographic positions — not GIS accurate": some
 * positions are real (ports, growing regions), others are illustrative. Entity
 * placements declared in the PDL/roster take precedence over this fallback.
 *
 * Resolution follows the THREE-outcome rule (never two):
 *   1. Known entity      -> real coordinates, rendered normally.
 *   2. Known-illustrative -> chosen position, `illustrative: true`, visible marking.
 *   3. Unknown entity    -> NOT rendered, a warning is logged. Never fall back to a
 *      country centroid: a confident wrong placement is worse than a visible gap.
 */

import type { Edge, GeoCoord, Node } from './types'

export interface GazEntry {
  lat: number
  lng: number
  /** English display name for this entity's marker. */
  label: string
  /** True when the position is a chosen approximation, not a real location. */
  illustrative: boolean
}

/**
 * Fallback position by PDL entity id. Ports and growing regions are real; EU
 * processing entities are illustrative (no location in the sim). The three
 * livestock entities are given distinct illustrative spots around the branch-21
 * EuFarmers anchor (46.5, 2.5) so the pooled node splits into three markers.
 */
export const GAZETTEER: Record<string, GazEntry> = {
  // Producers — real growing regions
  brazil_farms: { lat: -13.0, lng: -56.0, label: 'Brazil soy farms', illustrative: false },
  argentina_farms: { lat: -34.0, lng: -62.0, label: 'Argentina soy farms', illustrative: false },
  us_farms: { lat: 42.0, lng: -93.0, label: 'US soy farms', illustrative: false },

  // Ports — real locations
  santos_port: { lat: -24.0, lng: -46.3, label: 'Port of Santos', illustrative: false },
  paranagua_port: { lat: -25.5, lng: -48.5, label: 'Port of Paranaguá', illustrative: false },
  rotterdam_port: { lat: 51.95, lng: 4.14, label: 'Port of Rotterdam', illustrative: false },
  hamburg_port: { lat: 53.55, lng: 9.99, label: 'Port of Hamburg', illustrative: false },

  // EU processing — illustrative (no location in the sim data)
  eu_oil_mills: { lat: 52.0, lng: 4.5, label: 'EU oil mills', illustrative: true },
  feed_mills: { lat: 52.5, lng: 13.0, label: 'Feed mills', illustrative: true },

  // EU livestock — illustrative, three distinct spots so the pool splits visibly
  poultry_farms: { lat: 47.6, lng: 1.2, label: 'EU poultry farms', illustrative: true },
  pig_farms: { lat: 46.4, lng: 3.6, label: 'EU pig farms', illustrative: true },
  dairy_farms: { lat: 45.4, lng: 2.0, label: 'EU dairy farms', illustrative: true },
}

/** A single rendered marker (one node may yield several — see the pool split). */
export interface Marker {
  /** Unique marker id: node id, or `${nodeId}::${entityId}` for a split node. */
  id: string
  /** Owning bundle node id (the join key for time-series). */
  nodeId: string
  label: string
  role: string
  lat: number
  lng: number
  illustrative: boolean
  hasRecordedData: boolean
}

/** An edge with both endpoints resolved to coordinates, ready for `arcsData`. */
export interface ResolvedEdge {
  id: string
  startLat: number
  startLng: number
  endLat: number
  endLng: number
  isSeaCrossing: boolean
  /** "Source → Target" in English, for the edge annotation. */
  label: string
}

/** A node/edge that could not be placed, with the reason (for logging/UI). */
export interface Unplaced {
  kind: 'node' | 'edge'
  id: string
  reason: string
}

export interface Scene {
  markers: Marker[]
  edges: ResolvedEdge[]
  unplaced: Unplaced[]
}

/** Average of a node's marker coordinates — the endpoint an edge attaches to. */
function centroid(coords: GeoCoord[]): GeoCoord {
  const n = coords.length
  const sum = coords.reduce((a, c) => ({ lat: a.lat + c.lat, lng: a.lng + c.lng }), { lat: 0, lng: 0 })
  return { lat: sum.lat / n, lng: sum.lng / n }
}

/**
 * Resolve bundle nodes + edges into renderable markers + resolved edges. Declared
 * placements win over the fallback gazetteer. Unknown entities are dropped and
 * reported; an edge whose endpoint has no placement is likewise dropped.
 */
export function resolveScene(nodes: Node[], edges: Edge[]): Scene {
  const markers: Marker[] = []
  const unplaced: Unplaced[] = []
  const repById = new Map<string, GeoCoord>()

  for (const node of nodes) {
    const placed: GeoCoord[] = []

    if (node.entityIds.length === 0) {
      unplaced.push({ kind: 'node', id: node.id, reason: 'node has no entity ids' })
    } else {
      // One marker per entity id. A single-entity node yields one; a pooled node
      // (e.g. eu_farmers) yields several — the required 3-way livestock split.
      for (const eid of node.entityIds) {
        const g = node.placements.find((placement) => placement.entityId === eid) ?? GAZETTEER[eid]
        if (g) {
          const markerId = node.entityIds.length > 1 ? `${node.id}::${eid}` : node.id
          markers.push(toMarker(markerId, node, g))
          placed.push({ lat: g.lat, lng: g.lng })
        } else {
          unplaced.push({ kind: 'node', id: `${node.id} (${eid})`, reason: 'entity not in gazetteer' })
        }
      }
    }

    if (placed.length > 0) repById.set(node.id, centroid(placed))
  }

  const nameById = new Map(nodes.map((n) => [n.id, n.label]))
  const resolvedEdges: ResolvedEdge[] = []
  for (const e of edges) {
    const s = repById.get(e.source)
    const t = repById.get(e.target)
    if (!s || !t) {
      unplaced.push({ kind: 'edge', id: e.id, reason: 'endpoint has no placement' })
      continue
    }
    resolvedEdges.push({
      id: e.id,
      startLat: s.lat,
      startLng: s.lng,
      endLat: t.lat,
      endLng: t.lng,
      isSeaCrossing: e.isSeaCrossing,
      label: `${nameById.get(e.source) ?? e.source} → ${nameById.get(e.target) ?? e.target}`,
    })
  }

  return { markers, edges: resolvedEdges, unplaced }
}

function toMarker(id: string, node: Node, g: GazEntry): Marker {
  return {
    id,
    nodeId: node.id,
    label: g.label,
    role: node.role,
    lat: g.lat,
    lng: g.lng,
    illustrative: g.illustrative,
    hasRecordedData: node.hasRecordedData,
  }
}
