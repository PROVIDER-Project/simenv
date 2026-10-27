import type { FramePage, PlaybackSource, RunList, Scene } from './playback'
import { parseBundle } from './staticJsonSource'
import { measure } from '../playback/measure'

function object(value: unknown): asserts value is Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid playback object')
}
function integer(value: unknown): asserts value is number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Invalid playback integer')
}
function string(value: unknown): asserts value is string {
  if (typeof value !== 'string' || !value) throw new Error('Invalid playback string')
}

export function parseFramePage(input: unknown): FramePage {
  object(input); string(input.run_id); integer(input.scenario_id); integer(input.start)
  if (input.next_start !== null) integer(input.next_start)
  if (!Array.isArray(input.frames)) throw new Error('Invalid playback frames')
  let previous = input.start - 1
  for (const frame of input.frames) {
    object(frame); integer(frame.period)
    if (frame.period !== previous + 1 || !Array.isArray(frame.agents)) throw new Error('Invalid frame order')
    previous = frame.period
    const identities = new Set<string>()
    for (const agent of frame.agents) {
      object(agent); string(agent.entity_id); integer(agent.agent_id); string(agent.role); object(agent.values)
      const identity = JSON.stringify([agent.entity_id, agent.agent_id])
      if (identities.has(identity)) throw new Error('Duplicate agent state')
      identities.add(identity)
      for (const value of Object.values(agent.values)) {
        if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('Invalid recorded value')
      }
    }
  }
  return input as unknown as FramePage
}

function parseRuns(input: unknown): RunList {
  object(input); integer(input.total)
  if (!Array.isArray(input.items)) throw new Error('Invalid run catalogue')
  for (const run of input.items) {
    object(run); string(run.id); string(run.started_at); string(run.status); integer(run.period_num)
    if (typeof run.playable !== 'boolean' || !Array.isArray(run.scenario_ids)) throw new Error('Invalid run')
    run.scenario_ids.forEach(integer)
    for (const field of ['label', 'finished_at', 'unavailable_reason']) {
      if (run[field] !== null && typeof run[field] !== 'string') throw new Error('Invalid run metadata')
    }
  }
  return input as unknown as RunList
}

function parseScene(input: unknown): Scene {
  object(input); string(input.run_id); integer(input.scenario_id)
  integer(input.min_period); integer(input.max_period); string(input.pdl); string(input.honesty_note)
  if (input.max_period < input.min_period) throw new Error('Invalid period bounds')
  const bundle = parseBundle({ nodes: input.nodes, edges: input.edges, ticks: [], env: [],
    meta: { pdl: input.pdl, scenario: 'playback', ticks: 0, generatedAt: 'recorded', honestyNote: input.honesty_note } })
  return { ...input, nodes: bundle.nodes, edges: bundle.edges } as unknown as Scene
}

export function createHttpPlaybackSource(baseUrl: string): PlaybackSource {
  const base = baseUrl.replace(/\/$/, '')
  async function get<T>(path: string, parse: (input: unknown) => T, signal?: AbortSignal): Promise<T> {
    const started = performance.now()
    const response = await fetch(`${base}${path}`, { signal })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(typeof body.detail === 'string' ? body.detail : `Playback request failed (${response.status})`)
    }
    const text = await response.text()
    measure('playback.request', started)
    const decoding = performance.now()
    const data: unknown = JSON.parse(text)
    measure('playback.decode', decoding)
    const validation = performance.now()
    const parsed = parse(data)
    measure('playback.validate', validation)
    return parsed
  }
  const path = (run: string, scenario: number) => `/runs/${encodeURIComponent(run)}/scenarios/${scenario}`
  return {
    name: 'PostgreSQL playback',
    listRuns: (limit, offset, signal) => get(`/runs?limit=${limit}&offset=${offset}`, parseRuns, signal),
    getScene: (run, scenario, signal) => get(`${path(run, scenario)}/scene`, parseScene, signal),
    getFrames: async (run, scenario, start, limit, signal) => {
      const page = await get(`${path(run, scenario)}/frames?start=${start}&limit=${limit}`, parseFramePage, signal)
      if (page.run_id !== run || page.scenario_id !== scenario || page.start !== start || page.frames.length > limit) {
        throw new Error('Playback response identity or range mismatch')
      }
      return page
    },
  }
}
