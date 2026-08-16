/**
 * staticJsonSource — a `DataSource` backed by an exported `bundle.json`.
 *
 * This is the Batch-5 swap target: it reads the JSON the Python exporter
 * (`provider_simenv.export_bundle`) writes from a simulation run's CSVs, and is
 * selected at the composition root (`main.tsx`) without touching any view file.
 *
 * The fetched payload is untrusted input, so it crosses a structural check
 * (`parseBundle`) before any view sees it, rather than being cast blindly.
 */

import type { DataSource } from './source'
import type { Bundle, Edge, EnvState, Node, Tick } from './types'

const BUNDLE_URL = '/bundle.json'

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function requireArray(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`bundle.${field} must be an array`)
  return value
}

/** Validate the fetched payload at the trust boundary and return a typed Bundle. */
export function parseBundle(input: unknown): Bundle {
  if (!isObject(input)) throw new Error('bundle must be an object')
  if (!isObject(input.meta)) throw new Error('bundle.meta must be an object')

  const nodes = requireArray(input.nodes, 'nodes').map((n): Node => {
    if (!isObject(n)) throw new Error('bundle.nodes[] must be objects')
    return {
      id: String(n.id),
      label: String(n.label),
      role: String(n.role),
      entityIds: requireArray(n.entityIds, 'nodes[].entityIds').map(String),
      hasRecordedData: Boolean(n.hasRecordedData),
    }
  })

  const edges = requireArray(input.edges, 'edges').map((e): Edge => {
    if (!isObject(e)) throw new Error('bundle.edges[] must be objects')
    return {
      id: String(e.id),
      source: String(e.source),
      target: String(e.target),
      isSeaCrossing: Boolean(e.isSeaCrossing),
    }
  })

  const ticks = requireArray(input.ticks, 'ticks').map((t): Tick => {
    if (!isObject(t) || !isObject(t.values)) throw new Error('bundle.ticks[] malformed')
    return {
      period: Number(t.period),
      nodeId: String(t.nodeId),
      values: t.values as Record<string, number | boolean | null>,
    }
  })

  const env = requireArray(input.env, 'env').map((s): EnvState => {
    if (!isObject(s)) throw new Error('bundle.env[] must be objects')
    return {
      period: Number(s.period),
      sojaPrice: Number(s.sojaPrice),
      feedPrice: Number(s.feedPrice),
      shockScale: Number(s.shockScale),
      droughtSeverity: Number(s.droughtSeverity),
      totalSojaSupply: Number(s.totalSojaSupply),
      transportUtilisation: Number(s.transportUtilisation),
      currentStep: Number(s.currentStep),
    }
  })

  const meta = input.meta as Record<string, unknown>
  return {
    meta: {
      pdl: String(meta.pdl ?? ''),
      scenario: String(meta.scenario ?? ''),
      ticks: Number(meta.ticks ?? env.length),
      generatedAt: String(meta.generatedAt ?? ''),
      honestyNote: String(meta.honestyNote ?? ''),
    },
    nodes,
    edges,
    ticks,
    env,
  }
}

export const staticJsonSource: DataSource = {
  name: 'bundle.json',
  async getBundle(): Promise<Bundle> {
    const response = await fetch(BUNDLE_URL)
    if (!response.ok) throw new Error(`bundle request failed with HTTP ${response.status}`)
    const input: unknown = await response.json()
    return parseBundle(input)
  },
}
