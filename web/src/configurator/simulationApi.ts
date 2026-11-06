/** Submission and job contract from the simulation API (PR #50). */
export interface SimulationSubmission {
  pdl: string
  roster: string | null
  cascade: string
  label: string
}

export interface SimulationJob {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  label: string | null
  error: string | null
  progress: {
    scenario_id: number | null
    step: number
    scenario_total_steps: number
    completed_steps: number
    total_steps: number
    percent_complete: number
  }
}

const API_BASE = (import.meta.env?.VITE_SIMENV_API_BASE_URL || '/api').replace(/\/+$/, '')

export class SimulationApiError extends Error {
  constructor(message: string, public status: number | null, public operation: string) { super(message) }
  get ambiguous() { return this.operation === 'POST' && (this.status === null || this.status >= 500 || this.status < 300) }
}
export interface SimulationInputs {
  pdl: Record<string, unknown>
  roster: Record<string, unknown> | null
  cascade: string
  parameters: Record<string, number>
  current_parameters: Record<string, number>
  evidence: 'preserved' | 'execution-hashes'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseJob(value: unknown): SimulationJob {
  if (!isRecord(value) || typeof value.id !== 'string' || !value.id ||
      !['queued', 'running', 'completed', 'failed'].includes(String(value.status)) ||
      !(value.label === null || typeof value.label === 'string') ||
      !(value.error === null || typeof value.error === 'string') ||
      !isRecord(value.progress)) {
    throw new Error('Invalid simulation API response')
  }
  const progress = value.progress
  const counts = ['step', 'scenario_total_steps', 'completed_steps', 'total_steps']
  if (counts.some(key => !Number.isInteger(progress[key]) || Number(progress[key]) < 0) ||
      !(progress.scenario_id === null || Number.isInteger(progress.scenario_id)) ||
      typeof progress.percent_complete !== 'number' || !Number.isFinite(progress.percent_complete) ||
      progress.percent_complete < 0 || progress.percent_complete > 100) {
    throw new Error('Invalid simulation API response')
  }
  return value as unknown as SimulationJob
}

function errorDetail(value: unknown): string | null {
  if (!isRecord(value)) return null
  if (typeof value.detail === 'string') return value.detail
  if (Array.isArray(value.detail)) {
    return value.detail.flatMap(entry =>
      isRecord(entry) && typeof entry.msg === 'string' ? [entry.msg] : [],
    ).join('; ') || null
  }
  return null
}

async function request<T>(path: string, init: RequestInit, signal: AbortSignal, parse: (value: unknown) => T): Promise<T> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal.addEventListener('abort', abort, { once: true })
  if (signal.aborted) controller.abort()
  const timeout = window.setTimeout(abort, 15000)
  let status: number | null = null
  const operation = init.method || 'GET'
  try {
    const response = await fetch(`${API_BASE}/simulations${path}`, { ...init, signal: controller.signal })
    status = response.status
    const body: unknown = await response.json().catch(() => null)
    if (!response.ok) {
      throw new SimulationApiError(errorDetail(body) || `Simulation API request failed (HTTP ${response.status})`, status, operation)
    }
    return parse(body)
  } catch (error) {
    if (signal.aborted) throw error
    if (error instanceof SimulationApiError) throw error
    const text = controller.signal.aborted ? 'Simulation API request timed out'
      : error instanceof TypeError && status === null ? 'Cannot reach the simulation API. Check the service and API URL.'
        : error instanceof Error ? error.message : String(error)
    throw new SimulationApiError(text, status, operation)
  } finally {
    window.clearTimeout(timeout)
    signal.removeEventListener('abort', abort)
  }
}

export function submitSimulation(submission: SimulationSubmission, signal: AbortSignal) {
  return request('', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(submission),
  }, signal, parseJob)
}

export async function inspectSimulation(id: string, signal: AbortSignal) {
  const job = await request(`/${encodeURIComponent(id)}`, {}, signal, parseJob)
  if (job.id !== id) throw new Error('Invalid simulation API response: run ID changed')
  return job
}

export function getSimulationInputs(id: string, signal: AbortSignal): Promise<SimulationInputs> {
  return request(`/${encodeURIComponent(id)}/inputs`, {}, signal, value => {
    if (!isRecord(value) || !isRecord(value.pdl) || !(value.roster === null || isRecord(value.roster)) ||
      typeof value.cascade !== 'string' || !value.cascade || !isRecord(value.parameters) || !isRecord(value.current_parameters) ||
      !['preserved', 'execution-hashes'].includes(String(value.evidence))) throw new Error('Invalid preserved simulation inputs')
    for (const field of [value.parameters, value.current_parameters]) {
      if (!Object.keys(field).length || Object.values(field).some(v => typeof v !== 'number' || !Number.isFinite(v))) throw new Error('Invalid simulation parameters')
    }
    return value as unknown as SimulationInputs
  })
}

export function listSimulations(limit: number, offset: number, signal: AbortSignal) {
  return request(`?limit=${limit}&offset=${offset}`, {}, signal, value => {
    if (!isRecord(value) || !Array.isArray(value.items) || !Number.isSafeInteger(value.total) || Number(value.total) < 0 || value.items.length > limit) throw new Error('Invalid simulation history')
    return { items: value.items.map(parseJob), total: Number(value.total) }
  })
}
