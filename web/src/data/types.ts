/**
 * Frozen value objects for the world-map view (Issue #23).
 *
 * These types are the contract between the data layer (a `DataSource`) and every
 * view. They are shaped by the F1 schema audit of the Python model — see
 * `web/.planning/forge/PLAN.md` and the audit notes. Key facts baked in here:
 *
 *  - A node's stable identity is its **roster list name**. For a single-entity
 *    producer that is also the PDL entity id (e.g. "brazil_farms"). Sidecar-backed
 *    actors carry their declared entity id; pooled nodes (eu_farmers) keep one
 *    list name for several entities. `entityIds` carries the ids a node represents.
 *
 *  - Ports and sea-lanes are geographically real but carry **no recorded
 *    time-series** (they are absent from the model's DataCollector / TickWriter).
 *    `hasRecordedData` marks that so views never expect a series that isn't there.
 *
 *  - `eu_farmers` pools three PDL entities (poultry/pig/dairy) into ONE recorded
 *    series. On the map they may appear as several illustrative markers sharing
 *    that series; `positionIsIllustrative` marks any node whose coordinate is a
 *    chosen approximation rather than a real location.
 *
 *  - Per-tick fields differ by node type, so `Tick.values` is a keyed record
 *    rather than a fixed struct. That is the honest shape of the CSV data.
 */

/** A geographic coordinate. globe.gl consumes `lat` / `lng` directly. */
export interface GeoCoord {
  lat: number
  lng: number
}

/**
 * A supply-chain actor rendered on the map.
 *
 * `id` is the roster list name and is the join key for `Edge.source`/`Edge.target`
 * and for `Tick.nodeId`.
 */
export interface Node {
  /** Stable key = roster model-attr list name, e.g. "brazil_farms". */
  id: string
  /** Node-level English display name (used for edge labels), e.g. "Brazil soy farms". */
  label: string
  /** Agent role, e.g. "producer" | "wholesaler" | "sea_santos". */
  role: string
  /** PDL or sidecar entity ids this node represents. */
  entityIds: string[]
  /**
   * False for ports and sea-lanes, which exist structurally but produce no
   * per-tick rows. Views must not expect a time-series for these nodes.
   */
  hasRecordedData: boolean
}

/*
 * NOTE — coordinates are deliberately NOT on `Node`. Per the locked decision,
 * placement is a FRONTEND concern resolved from `gazetteer.ts` keyed by PDL
 * entity id, so a DataSource (fixture now, exported JSON / Postgres later) never
 * carries geography. This is the documented seam boundary: swapping the data
 * source can never move a marker.
 */

/**
 * A directed flow between two nodes in the derived supply-chain graph.
 *
 * `source`/`target` are roster list names.
 */
export interface Edge {
  /** Stable key, e.g. "brazil_farms->brazil_wholesaler". */
  id: string
  /** Upstream node id (the source of the flow). */
  source: string
  /** Downstream node id (the destination of the flow). */
  target: string
  /** True when this edge is an ocean crossing (a materialised sea-lane). */
  isSeaCrossing: boolean
}

/**
 * One recorded state snapshot for a single node at a single simulation step.
 *
 * `values` keys vary by node type — e.g. producers carry
 * `quantity_available` / `unit_price` / `active`; wholesalers additionally carry
 * storage utilisation; `eu_farmers` carries
 * `feed_received` / `livestock_output` / `active`.
 */
export interface Tick {
  /** Simulation step (the CSV `period`). */
  period: number
  /** Node id this snapshot belongs to. */
  nodeId: string
  /** Recorded properties for this node at this step. */
  values: Record<string, number | boolean | null>
}

/** One environment-level state snapshot for a single simulation step. */
export interface EnvState {
  period: number
  sojaPrice: number
  feedPrice: number
  shockScale: number
  droughtSeverity: number
  totalSojaSupply: number
  transportUtilisation: number
  currentStep: number
}

/** Metadata describing the run a bundle came from. */
export interface BundleMeta {
  /** PDL file the run was driven by, e.g. "s1-soja.pdl.yaml". */
  pdl: string
  /** Scenario id, e.g. "soy_feed_disruption". */
  scenario: string
  /** Number of simulation steps present in `ticks` / `env`. */
  ticks: number
  /** ISO timestamp the bundle was produced. */
  generatedAt: string
  /** On-screen honesty note about approximate positions. */
  honestyNote: string
}

/**
 * The complete payload a `DataSource` yields: the map's nodes and edges, plus the
 * per-node and environment time-series for the whole run.
 */
export interface Bundle {
  meta: BundleMeta
  nodes: Node[]
  edges: Edge[]
  ticks: Tick[]
  env: EnvState[]
}
