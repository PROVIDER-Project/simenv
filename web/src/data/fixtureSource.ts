/**
 * fixtureSource — a hand-written `DataSource` for developing views before the
 * real Python exporter exists (Batch 5 replaces this with `staticJsonSource`).
 *
 * The fixture is deliberately shaped to exercise every awkward case the F1 audit
 * surfaced, so views are correct from day one rather than only against the happy
 * path:
 *
 *   - `transport_sa_santos` and `transport_eu_rtm` are ports: real coordinates,
 *     but `hasRecordedData: false` and NO entries in `ticks`. Views must render
 *     them without expecting a series.
 *   - `wholesalers` is a synthetic hub: `entityIds: []`, illustrative position.
 *   - `eu_farmers` is a pooled consumer: three `entityIds`, illustrative position,
 *     ONE recorded series.
 *   - one edge is an ocean crossing (`isSeaCrossing: true`).
 *
 * The flow spine is collapsed for the fixture (e.g. the Santos→Rotterdam crossing
 * is drawn as a single sea edge rather than routed through a `sea_lane_*` node,
 * and the EU processing tail skips `feed_manufacturers`/`feed_traders`). The real
 * exporter will emit the full model graph; this is illustrative scaffolding.
 */

import type { DataSource } from './source'
import type { Bundle, EnvState, Node, Tick } from './types'

const HONESTY_NOTE = 'Approximate geographic positions — not GIS accurate'

const PERIODS = [0, 1, 2] as const

// The full geolocatable roster (from the F1 audit). Node `label`s are node-level
// English names (used for edge annotations); per-marker display names +
// coordinates come from the gazetteer, keyed by the entity ids below. Ports and
// sea-lanes carry no recorded series (`hasRecordedData: false`). `food_retail` is
// deliberately an entity the gazetteer does NOT know, to keep exercising outcome
// 3 (drop + warn) end-to-end. The real exporter (Batch 5) emits this same shape.
const nodes: Node[] = [
  // Producers (real coords, recorded data)
  { id: 'bra_farmers', label: 'Brazil soy farms', role: 'producer', entityIds: ['brazil_farms'], hasRecordedData: true },
  { id: 'arg_farmers', label: 'Argentina soy farms', role: 'producer', entityIds: ['argentina_farms'], hasRecordedData: true },
  { id: 'usa_farmers', label: 'US soy farms', role: 'producer', entityIds: ['us_farms'], hasRecordedData: true },
  // Synthetic hubs (illustrative, recorded data)
  { id: 'wholesalers', label: 'Wholesalers', role: 'wholesaler', entityIds: [], hasRecordedData: true },
  { id: 'feed_traders', label: 'Feed traders', role: 'feed_trader', entityIds: [], hasRecordedData: true },
  // Ports (real coords, NO recorded data)
  { id: 'transport_sa_santos', label: 'Port of Santos', role: 'sa_santos', entityIds: ['santos_port'], hasRecordedData: false },
  { id: 'transport_sa_paranagua', label: 'Port of Paranaguá', role: 'sa_paranagua', entityIds: ['paranagua_port'], hasRecordedData: false },
  { id: 'transport_eu_rtm', label: 'Port of Rotterdam', role: 'eu_rtm', entityIds: ['rotterdam_port'], hasRecordedData: false },
  { id: 'transport_eu_ham', label: 'Port of Hamburg', role: 'eu_ham', entityIds: ['hamburg_port'], hasRecordedData: false },
  // EU processing (illustrative, recorded data)
  { id: 'processors', label: 'EU oil mills', role: 'processor', entityIds: ['eu_oil_mills'], hasRecordedData: true },
  { id: 'feed_manufacturers', label: 'Feed mills', role: 'feed_manufacturer', entityIds: ['feed_mills'], hasRecordedData: true },
  // EU livestock — pooled, splits into three illustrative markers
  { id: 'eu_farmers', label: 'EU livestock farms', role: 'consumer', entityIds: ['poultry_farms', 'pig_farms', 'dairy_farms'], hasRecordedData: true },
  // Unknown entity — must NOT render; resolveScene should log a warning.
  { id: 'food_retail', label: 'Food retail', role: 'service', entityIds: ['food_retail'], hasRecordedData: false },
]

const edges = [
  // Producers -> market hub
  { id: 'bra_farmers->wholesalers', source: 'bra_farmers', target: 'wholesalers', isSeaCrossing: false },
  { id: 'arg_farmers->wholesalers', source: 'arg_farmers', target: 'wholesalers', isSeaCrossing: false },
  { id: 'usa_farmers->wholesalers', source: 'usa_farmers', target: 'wholesalers', isSeaCrossing: false },
  // Hub -> export ports
  { id: 'wholesalers->transport_sa_santos', source: 'wholesalers', target: 'transport_sa_santos', isSeaCrossing: false },
  { id: 'wholesalers->transport_sa_paranagua', source: 'wholesalers', target: 'transport_sa_paranagua', isSeaCrossing: false },
  // Atlantic sea crossings (materialised sea-lanes, collapsed to port->port here)
  { id: 'transport_sa_santos->transport_eu_rtm', source: 'transport_sa_santos', target: 'transport_eu_rtm', isSeaCrossing: true },
  { id: 'transport_sa_paranagua->transport_eu_ham', source: 'transport_sa_paranagua', target: 'transport_eu_ham', isSeaCrossing: true },
  // Argentina alt route + US emergency route (direct sea bypass to Rotterdam)
  { id: 'arg_farmers->transport_eu_rtm', source: 'arg_farmers', target: 'transport_eu_rtm', isSeaCrossing: true },
  { id: 'usa_farmers->transport_eu_rtm', source: 'usa_farmers', target: 'transport_eu_rtm', isSeaCrossing: true },
  // EU processing chain
  { id: 'transport_eu_rtm->processors', source: 'transport_eu_rtm', target: 'processors', isSeaCrossing: false },
  { id: 'transport_eu_ham->processors', source: 'transport_eu_ham', target: 'processors', isSeaCrossing: false },
  { id: 'processors->feed_manufacturers', source: 'processors', target: 'feed_manufacturers', isSeaCrossing: false },
  { id: 'feed_manufacturers->feed_traders', source: 'feed_manufacturers', target: 'feed_traders', isSeaCrossing: false },
  { id: 'feed_traders->eu_farmers', source: 'feed_traders', target: 'eu_farmers', isSeaCrossing: false },
  // Edge into the unknown node — must be dropped (endpoint has no placement).
  { id: 'eu_farmers->food_retail', source: 'eu_farmers', target: 'food_retail', isSeaCrossing: false },
]

/**
 * Per-node per-tick values, one small ramp per period so views have something
 * that changes over time. Keys match the recorded CSV schema for each node type
 * (see F1). Ports carry no series and are intentionally absent.
 */
function valuesFor(nodeId: string, period: number): Record<string, number | boolean | null> | null {
  const k = period // 0,1,2 — a tiny deterministic ramp
  switch (nodeId) {
    case 'bra_farmers':
      return { quantity_available: 100.0 - 5 * k, unit_price: 396.0 + 12 * k, active: true }
    case 'arg_farmers':
      return { quantity_available: 100.0 - 3 * k, unit_price: 462.0 + 10 * k, active: true }
    case 'usa_farmers':
      return { quantity_available: 100.0 + 4 * k, unit_price: 528.0 - 8 * k, active: true }
    case 'feed_manufacturers':
      return { quantity_available: 213.3 - 6 * k, unit_price: 1212.1 + 34 * k }
    case 'feed_traders':
      return { quantity_available: 213.3 - 6 * k, unit_price: 1349.6 + 40 * k }
    case 'wholesalers':
      return {
        quantity_available: 766.7 - 20 * k,
        unit_price: 523.4 + 15 * k,
        bra_volume: 333.3 - 10 * k,
        arg_volume: 166.7,
        usa_volume: 266.7 + 10 * k,
        storage_utilization: 0.268 - 0.007 * k,
      }
    case 'processors':
      return { quantity_available: 213.3 - 6 * k, unit_price: 1045.7 + 30 * k }
    case 'eu_farmers':
      return { feed_received: 64.0 - 2 * k, livestock_output: 64.0 - 2 * k, active: true }
    default:
      return null // ports / anything without a recorded series
  }
}

const ticks: Tick[] = []
for (const n of nodes) {
  if (!n.hasRecordedData) continue
  for (const period of PERIODS) {
    const values = valuesFor(n.id, period)
    if (values !== null) ticks.push({ period, nodeId: n.id, values })
  }
}

const env: EnvState[] = PERIODS.map((period) => ({
  period,
  sojaPrice: 523.4 + 15 * period,
  feedPrice: 1349.6 + 40 * period,
  shockScale: 0.0,
  droughtSeverity: 0.0,
  totalSojaSupply: 2300.0 - 60 * period,
  transportUtilisation: 0.6625,
  currentStep: period + 1,
}))

const bundle: Bundle = {
  meta: {
    pdl: 's1-soja.pdl.yaml',
    scenario: 'soy_feed_disruption',
    ticks: PERIODS.length,
    generatedAt: '2026-07-28T00:00:00Z',
    honestyNote: HONESTY_NOTE,
  },
  nodes,
  edges,
  ticks,
  env,
}

export const fixtureSource: DataSource = {
  name: 'fixture',
  getBundle(): Promise<Bundle> {
    return Promise.resolve(bundle)
  },
}
