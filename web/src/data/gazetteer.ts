/**
 * Frontend coordinate authority, keyed by PDL entity id. Positions stay out of
 * the bundle so data-source changes cannot move markers.
 *
 * Resolution has three outcomes: known, known-illustrative, or unplaced. Unknown
 * entities are never replaced with a country centroid; a confident wrong
 * placement is worse than a visible gap.
 */

import type { Edge, GeoCoord, Node } from './types'

export interface GazEntry {
  lat: number
  lng: number
  /** English display name for this entity's marker. */
  label: string
  /** True when the position is a chosen approximation, not a real location. */
  illustrative: boolean
  /** PDL location key used for structural geographic attribution. */
  pdlLocation?: string
}

/**
 * PDL entity id -> position. Ports and growing regions are real; EU processing
 * entities are illustrative (no location in the sim). The three livestock
 * entities are given distinct illustrative spots around the branch-21 EuFarmers
 * anchor (46.5, 2.5) so the pooled `eu_farmers` node splits into three markers.
 */
export const GAZETTEER: Record<string, GazEntry> = {
  // Producers — real growing regions
  brazil_farms: { lat: -13.0, lng: -56.0, label: 'Brazil soy farms', illustrative: false, pdlLocation: 'Brazil' },
  argentina_farms: { lat: -34.0, lng: -62.0, label: 'Argentina soy farms', illustrative: false, pdlLocation: 'Argentina' },
  us_farms: { lat: 42.0, lng: -93.0, label: 'US soy farms', illustrative: false, pdlLocation: 'United States' },

  // Ports — real locations
  santos_port: { lat: -24.0, lng: -46.3, label: 'Port of Santos', illustrative: false, pdlLocation: 'Brazil' },
  paranagua_port: { lat: -25.5, lng: -48.5, label: 'Port of Paranaguá', illustrative: false, pdlLocation: 'Brazil' },
  // Placement source only: the Argentina lane departs from Buenos Aires, not the inland farm node.
  argentina_port: { lat: -34.7, lng: -58.3, label: 'Port of Buenos Aires', illustrative: false },
  // Placement source only: EXCLUDE keeps this PDL entity out of the rendered roster.
  us_gulf_ports: { lat: 29.95, lng: -90.07, label: 'Port of New Orleans', illustrative: false, pdlLocation: 'United States' },
  rotterdam_port: { lat: 51.95, lng: 4.14, label: 'Port of Rotterdam', illustrative: false, pdlLocation: 'Netherlands' },
  hamburg_port: { lat: 53.55, lng: 9.99, label: 'Port of Hamburg', illustrative: false, pdlLocation: 'Germany' },

  // EU processing — illustrative (no location in the sim data)
  eu_oil_mills: { lat: 52.0, lng: 4.5, label: 'EU oil mills', illustrative: true, pdlLocation: 'EU' },
  feed_mills: { lat: 52.5, lng: 13.0, label: 'Feed mills', illustrative: true, pdlLocation: 'EU' },

  // EU livestock — illustrative, three distinct spots so the pool splits visibly
  poultry_farms: { lat: 47.6, lng: 1.2, label: 'EU poultry farms', illustrative: true, pdlLocation: 'EU' },
  pig_farms: { lat: 46.4, lng: 3.6, label: 'EU pig farms', illustrative: true, pdlLocation: 'EU' },
  dairy_farms: { lat: 45.4, lng: 2.0, label: 'EU dairy farms', illustrative: true, pdlLocation: 'EU' },
}

/**
 * Synthetic hubs have no PDL entity, so they are keyed by roster list name and
 * are always illustrative (they are model constructs, not places).
 */
export const SYNTHETIC_PLACEMENTS: Record<string, GazEntry> = {
  wholesalers: { lat: -23.0, lng: -47.0, label: 'Wholesalers (hub)', illustrative: true },
  feed_traders: { lat: 47.5, lng: 16.0, label: 'Feed traders (hub)', illustrative: true },
}

type LaneCrossing = readonly [sourceEntityId: string, targetEntityId: string]

/**
 * Frontend mirror of topology.py's TRANSITIONAL_SEA crossing-to-lane mapping.
 * The placement contract checks it against the PDL-derived mapping so the two
 * authorities cannot drift silently.
 */
export const PROVISIONAL_LANE_CROSSINGS = {
  sea_lane_santos: ['santos_port', 'rotterdam_port'],
  sea_lane_paranagua: ['paranagua_port', 'hamburg_port'],
  sea_lane_arg: ['argentina_farms', 'rotterdam_port'],
  sea_lane_usa: ['us_gulf_ports', 'rotterdam_port'],
} as const satisfies Record<string, LaneCrossing>

/** Base split fractions for lanes whose inbound edge is visible. */
export const PROVISIONAL_LANE_FRACTIONS: Record<string, number> = {
  sea_lane_santos: 0.4,
  sea_lane_paranagua: 0.6,
  sea_lane_arg: 0.5,
  sea_lane_usa: 0.5,
}

function greatCirclePoint(start: GeoCoord, end: GeoCoord, fraction: number): GeoCoord {
  if (fraction < 0 || fraction > 1) {
    throw new Error(`Great-circle fraction must be between 0 and 1, received ${fraction}`)
  }
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180
  const toDegrees = (radians: number) => (radians * 180) / Math.PI
  const startLat = toRadians(start.lat)
  const startLng = toRadians(start.lng)
  const endLat = toRadians(end.lat)
  const endLng = toRadians(end.lng)
  const startVector = [
    Math.cos(startLat) * Math.cos(startLng),
    Math.cos(startLat) * Math.sin(startLng),
    Math.sin(startLat),
  ]
  const endVector = [
    Math.cos(endLat) * Math.cos(endLng),
    Math.cos(endLat) * Math.sin(endLng),
    Math.sin(endLat),
  ]
  const dot = Math.min(
    1,
    Math.max(-1, startVector.reduce((sum, value, index) => sum + value * endVector[index], 0)),
  )
  const angle = Math.acos(dot)
  if (angle < Number.EPSILON) return { ...start }

  const sinAngle = Math.sin(angle)
  const startWeight = Math.sin((1 - fraction) * angle) / sinAngle
  const endWeight = Math.sin(fraction * angle) / sinAngle
  const [x, y, z] = startVector.map(
    (value, index) => startWeight * value + endWeight * endVector[index],
  )
  return {
    lat: toDegrees(Math.atan2(z, Math.hypot(x, y))),
    lng: toDegrees(Math.atan2(y, x)),
  }
}

function gazetteerCoord(entityId: string): GeoCoord {
  const entry = GAZETTEER[entityId]
  if (!entry) throw new Error(`Lane waypoint source is absent: ${entityId}`)
  return { lat: entry.lat, lng: entry.lng }
}

/**
 * Four authored shipping routes. Endpoints come from each lane's PDL crossing;
 * the intermediate points keep the Brazilian routes offshore, start Argentina
 * through the Rio de la Plata, and take the US Gulf route through Florida.
 */
export const LANE_WAYPOINTS = {
  sea_lane_santos: [
    gazetteerCoord('santos_port'),
    { lat: -23.0, lng: -41.0 },
    { lat: -17.0, lng: -33.0 },
    { lat: -6.0, lng: -27.0 },
    { lat: 8.0, lng: -23.0 },
    { lat: 22.0, lng: -20.0 },
    { lat: 36.0, lng: -16.0 },
    { lat: 45.0, lng: -12.0 },
    { lat: 49.0, lng: -7.0 },
    { lat: 50.5, lng: -2.0 },
    { lat: 51.2, lng: 1.4 },
    gazetteerCoord('rotterdam_port'),
  ],
  sea_lane_paranagua: [
    gazetteerCoord('paranagua_port'),
    { lat: -28.0, lng: -42.0 },
    { lat: -24.0, lng: -34.0 },
    { lat: -14.0, lng: -26.0 },
    { lat: -1.0, lng: -20.0 },
    { lat: 14.0, lng: -17.0 },
    { lat: 29.0, lng: -13.0 },
    { lat: 42.0, lng: -8.0 },
    { lat: 49.0, lng: -3.0 },
    { lat: 52.0, lng: 3.0 },
    { lat: 53.0, lng: 6.0 },
    gazetteerCoord('hamburg_port'),
  ],
  sea_lane_arg: [
    gazetteerCoord('argentina_port'),
    { lat: -37.0, lng: -54.0 },
    { lat: -32.0, lng: -49.0 },
    { lat: -23.0, lng: -44.0 },
    { lat: -12.0, lng: -38.0 },
    { lat: 1.0, lng: -33.0 },
    { lat: 16.0, lng: -29.0 },
    { lat: 31.0, lng: -25.0 },
    { lat: 43.0, lng: -20.0 },
    { lat: 48.0, lng: -13.0 },
    { lat: 50.0, lng: -6.0 },
    gazetteerCoord('rotterdam_port'),
  ],
  sea_lane_usa: [
    gazetteerCoord('us_gulf_ports'),
    { lat: 25.5, lng: -84.0 },
    { lat: 24.0, lng: -80.0 },
    { lat: 29.0, lng: -71.0 },
    { lat: 35.0, lng: -58.0 },
    { lat: 41.0, lng: -44.0 },
    { lat: 46.0, lng: -30.0 },
    { lat: 49.0, lng: -17.0 },
    { lat: 50.5, lng: -7.0 },
    { lat: 51.2, lng: -1.0 },
    gazetteerCoord('rotterdam_port'),
  ],
} as const satisfies Record<keyof typeof PROVISIONAL_LANE_CROSSINGS, readonly GeoCoord[]>

interface LaneRoute {
  node: GeoCoord
  toNode: GeoCoord[]
  fromNode: GeoCoord[]
}

function greatCircleRadians(start: GeoCoord, end: GeoCoord): number {
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180
  const startLat = toRadians(start.lat)
  const endLat = toRadians(end.lat)
  const deltaLng = toRadians(end.lng - start.lng)
  const cosine =
    Math.sin(startLat) * Math.sin(endLat) +
    Math.cos(startLat) * Math.cos(endLat) * Math.cos(deltaLng)
  return Math.acos(Math.min(1, Math.max(-1, cosine)))
}

/** Split a waypoint line at a fraction of its total great-circle surface length. */
function splitLaneRoute(points: readonly GeoCoord[], nodeFraction: number): LaneRoute {
  if (nodeFraction <= 0 || nodeFraction >= 1) {
    throw new Error(`Lane node fraction must be between 0 and 1, received ${nodeFraction}`)
  }
  const lengths = points.slice(1).map((point, index) => greatCircleRadians(points[index], point))
  const nodeDistance = lengths.reduce((sum, length) => sum + length, 0) * nodeFraction
  let travelled = 0

  for (let index = 1; index < points.length; index += 1) {
    const length = lengths[index - 1]
    if (travelled + length >= nodeDistance) {
      const fraction = length === 0 ? 0 : (nodeDistance - travelled) / length
      const node = greatCirclePoint(points[index - 1], points[index], fraction)
      return {
        node,
        toNode: [...points.slice(0, index), node],
        fromNode: [node, ...points.slice(index)],
      }
    }
    travelled += length
  }

  throw new Error('Lane waypoint line must contain two distinct positions')
}

const COMMERCIAL_LANE_ORIGIN_FRACTION = 0.04

/** Build only routes active in this bundle; inbound kind determines where the lane becomes visible. */
function buildLaneRoutes(nodes: Node[], edges: Edge[]): Record<string, LaneRoute> {
  const routes: Record<string, LaneRoute> = {}
  const waypointsByLane = LANE_WAYPOINTS as Record<string, readonly GeoCoord[]>

  for (const node of nodes) {
    if (!node.role.startsWith('sea_')) continue
    const waypoints = waypointsByLane[node.id]
    if (!waypoints) continue
    const inbound = edges.find((edge) => edge.target === node.id)
    const baseFraction = PROVISIONAL_LANE_FRACTIONS[node.id] ?? 0.5
    const nodeFraction =
      inbound?.kind === 'commercial' ? COMMERCIAL_LANE_ORIGIN_FRACTION : baseFraction
    routes[node.id] = splitLaneRoute(waypoints, nodeFraction)
  }

  return routes
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

/** A route-derived port marker. It is presentation geometry, never a bundle node. */
export interface RoutePortMarker {
  id: string
  label: string
  role: 'origin' | 'destination'
  lat: number
  lng: number
}

/** An edge with both endpoints resolved to coordinates, ready for globe layers. */
export interface ResolvedEdge {
  id: string
  sourceId: string
  targetId: string
  startLat: number
  startLng: number
  endLat: number
  endLng: number
  kind: Edge['kind']
  isSeaCrossing: boolean
  /** Lane endpoint derived from node role; absent on non-lane edges. */
  laneNodeId?: string
  /** Authored half-route for a physical lane edge; absent means arc fallback. */
  path?: readonly GeoCoord[]
}

/** A node/edge that could not be placed, with the reason (for logging/UI). */
export interface Unplaced {
  kind: 'node' | 'edge'
  id: string
  reason: string
}

export interface Scene {
  markers: Marker[]
  routePortMarkers: RoutePortMarker[]
  edges: ResolvedEdge[]
  commercialGroups: CommercialGroup[]
  unplaced: Unplaced[]
}

export interface CommercialGroup {
  id: string
  label: string
  edgeIds: string[]
}

interface GazEntryMatch {
  entityId?: string
  entry: GazEntry
}

function gazetteerEntryAt(point: GeoCoord): GazEntryMatch | undefined {
  const match = Object.entries(GAZETTEER).find(
    ([, entry]) => entry.lat === point.lat && entry.lng === point.lng,
  )
  return match ? { entityId: match[0], entry: match[1] } : undefined
}

/** Port markers deduplicated from the endpoints of routes active in this scene. */
function buildRoutePortMarkers(
  routes: Record<string, LaneRoute>,
  nodes: Node[],
  markers: Marker[],
): RoutePortMarker[] {
  const seen = new Map<string, RoutePortMarker>()
  const resolvedNodeIds = new Set(markers.map((marker) => marker.nodeId))
  const resolvedEntityIds = new Set(
    nodes
      .filter((node) => resolvedNodeIds.has(node.id))
      .flatMap((node) => node.entityIds),
  )

  for (const route of Object.values(routes)) {
    const endpoints = [
      { role: 'origin' as const, point: route.toNode[0] },
      {
        role: 'destination' as const,
        point: route.fromNode[route.fromNode.length - 1],
      },
    ]
    for (const endpoint of endpoints) {
      const source = gazetteerEntryAt(endpoint.point)
      if (!source) throw new Error('Route endpoint is absent from the gazetteer')
      const represented = source.entityId
        ? resolvedEntityIds.has(source.entityId)
        : markers.some(
            (marker) =>
              Math.hypot(marker.lat - endpoint.point.lat, marker.lng - endpoint.point.lng) < 0.01,
          )
      if (represented) continue
      const key = `${endpoint.role}@${endpoint.point.lat},${endpoint.point.lng}`
      if (!seen.has(key)) {
        seen.set(key, {
          id: `route-port:${key}`,
          label: source.entry.label,
          role: endpoint.role,
          lat: endpoint.point.lat,
          lng: endpoint.point.lng,
        })
      }
    }
  }

  return [...seen.values()]
}

const LOCATION_LABELS: Record<string, string> = {
  'United States': 'USA',
}

function displayLocation(location: string): string {
  return LOCATION_LABELS[location] ?? location
}

function nodeLocations(node: Node): string[] {
  const crossings = PROVISIONAL_LANE_CROSSINGS as Record<string, LaneCrossing>
  const crossing = node.role.startsWith('sea_') ? crossings[node.id] : undefined
  const entityIds = crossing ? [crossing[0]] : node.entityIds
  return [
    ...new Set(
      entityIds.flatMap((entityId) => {
        const location = GAZETTEER[entityId]?.pdlLocation
        return location ? [location] : []
      }),
    ),
  ]
}

/** Partition visible commercial edges without assigning edge ids by hand. */
function buildCommercialGroups(nodes: Node[], edges: ResolvedEdge[]): CommercialGroup[] {
  const nodesById = new Map(nodes.map((node) => [node.id, node]))
  const producers = nodes.filter((node) => node.role === 'producer')
  const producerByLocation = new Map<string, Node>()
  for (const producer of producers) {
    for (const location of nodeLocations(producer)) producerByLocation.set(location, producer)
  }

  const edgeIdsByProducer = new Map<string, string[]>()
  const unattributed: ResolvedEdge[] = []
  for (const edge of edges) {
    if (edge.kind !== 'commercial') continue
    const source = nodesById.get(edge.sourceId)
    const target = nodesById.get(edge.targetId)
    const directProducer = source?.role === 'producer' ? source : target?.role === 'producer' ? target : undefined
    const geographicProducer = target
      ? nodeLocations(target).map((location) => producerByLocation.get(location)).find(Boolean)
      : undefined
    const producer = directProducer ?? geographicProducer
    if (!producer) {
      unattributed.push(edge)
      continue
    }
    const ids = edgeIdsByProducer.get(producer.id) ?? []
    ids.push(edge.id)
    edgeIdsByProducer.set(producer.id, ids)
  }

  const groups: CommercialGroup[] = producers.flatMap((producer) => {
    const edgeIds = edgeIdsByProducer.get(producer.id)
    const location = nodeLocations(producer)[0]
    return edgeIds && location
      ? [{ id: `producer:${producer.id}`, label: displayLocation(location), edgeIds }]
      : []
  })

  const pending = [...unattributed]
  while (pending.length > 0) {
    const component = [pending.shift()!]
    const nodeIds = new Set([component[0].sourceId, component[0].targetId])
    for (let index = 0; index < pending.length; ) {
      const edge = pending[index]
      if (nodeIds.has(edge.sourceId) || nodeIds.has(edge.targetId)) {
        component.push(edge)
        nodeIds.add(edge.sourceId)
        nodeIds.add(edge.targetId)
        pending.splice(index, 1)
        index = 0
      } else {
        index += 1
      }
    }
    const locations = [
      ...new Set(
        [...nodeIds].flatMap((nodeId) => {
          const node = nodesById.get(nodeId)
          return node ? nodeLocations(node) : []
        }),
      ),
    ]
    const location = locations.length === 1 ? locations[0] : undefined
    const key = location ?? component.map((edge) => edge.id).sort().join('|')
    groups.push({
      id: `distribution:${key.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
      label: location ? `${displayLocation(location)} distribution` : 'Distribution',
      edgeIds: component.map((edge) => edge.id),
    })
  }

  return groups
}

/** Average of a node's marker coordinates — the endpoint an edge attaches to. */
function centroid(coords: GeoCoord[]): GeoCoord {
  const n = coords.length
  const sum = coords.reduce((a, c) => ({ lat: a.lat + c.lat, lng: a.lng + c.lng }), { lat: 0, lng: 0 })
  return { lat: sum.lat / n, lng: sum.lng / n }
}

/**
 * Resolve bundle nodes + edges into renderable markers + resolved edges, applying
 * the three-outcome rule. Unknown entities are dropped and reported (outcome 3);
 * an edge whose source or target has no placement is likewise dropped.
 */
export function resolveScene(nodes: Node[], edges: Edge[]): Scene {
  const markers: Marker[] = []
  const unplaced: Unplaced[] = []
  const repById = new Map<string, GeoCoord>()
  const laneRoutes = buildLaneRoutes(nodes, edges)
  const nodesById = new Map(nodes.map((node) => [node.id, node]))
  const lanePlacements: Record<string, GazEntry> = Object.fromEntries(
    Object.entries(laneRoutes).map(([laneId, route]) => [
      laneId,
      { ...route.node, label: nodesById.get(laneId)?.label ?? laneId, illustrative: false },
    ]),
  )
  const laneNodeIds = new Set(
    nodes.filter((node) => node.role.startsWith('sea_')).map((node) => node.id),
  )

  for (const node of nodes) {
    const placed: GeoCoord[] = []

    if (node.entityIds.length === 0) {
      // Synthetic hubs and materialised lanes are keyed by roster list name.
      const g = SYNTHETIC_PLACEMENTS[node.id] ?? lanePlacements[node.id]
      if (g) {
        markers.push(toMarker(node.id, node, g))
        placed.push({ lat: g.lat, lng: g.lng })
      } else {
        unplaced.push({ kind: 'node', id: node.id, reason: 'synthetic hub with no placement' })
      }
    } else {
      // One marker per entity id. A single-entity node yields one; a pooled node
      // (e.g. eu_farmers) yields several — the required 3-way livestock split.
      for (const eid of node.entityIds) {
        const g = GAZETTEER[eid]
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

  const resolvedEdges: ResolvedEdge[] = []
  for (const e of edges) {
    const s = repById.get(e.source)
    const t = repById.get(e.target)
    if (!s || !t) {
      unplaced.push({ kind: 'edge', id: e.id, reason: 'endpoint has no placement' })
      continue
    }
    const laneNodeId = laneNodeIds.has(e.source)
      ? e.source
      : laneNodeIds.has(e.target)
        ? e.target
        : undefined
    const route = laneNodeId ? laneRoutes[laneNodeId] : undefined
    const path =
      e.kind === 'physical' && route
        ? e.target === laneNodeId
          ? route.toNode
          : route.fromNode
        : undefined

    resolvedEdges.push({
      id: e.id,
      sourceId: e.source,
      targetId: e.target,
      startLat: s.lat,
      startLng: s.lng,
      endLat: t.lat,
      endLng: t.lng,
      kind: e.kind,
      isSeaCrossing: e.isSeaCrossing,
      laneNodeId,
      path,
    })
  }

  return {
    markers,
    routePortMarkers: buildRoutePortMarkers(laneRoutes, nodes, markers),
    edges: resolvedEdges,
    commercialGroups: buildCommercialGroups(nodes, resolvedEdges),
    unplaced,
  }
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
