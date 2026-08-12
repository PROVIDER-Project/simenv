export interface GeoCoord {
  lat: number
  lng: number
}

export interface Node {
  id: string
  label: string
  role: string
  entityIds: string[]
  hasRecordedData: boolean
}

export interface Edge {
  id: string
  source: string
  target: string
  /**
   * `commercial` means at least one endpoint is a synthetic node with no real
   * location, so no geographic route can be drawn. Goods still move on every
   * edge: the wholesaler holds inventory and records `quantity_available` and
   * `storage_utilization`. #24 must not interpret this as money flow; money is
   * recorded nowhere. Renaming is deferred to that ticket.
   */
  kind: 'commercial' | 'physical'
  /**
   * @deprecated The crossing is represented by a lane node identified by its
   * role. This legacy lane-incidence flag can contradict `kind`; renderers must
   * derive lane incidence from endpoint node roles instead.
   */
  isSeaCrossing: boolean
}

export interface Tick {
  period: number
  nodeId: string
  // Fields differ by agent type; the CSV exporter preserves that sparse shape.
  values: Record<string, number | boolean | null>
}

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

export interface BundleMeta {
  pdl: string
  scenario: string
  ticks: number
  generatedAt: string
  honestyNote: string
}

export interface Bundle {
  meta: BundleMeta
  nodes: Node[]
  edges: Edge[]
  ticks: Tick[]
  env: EnvState[]
}
