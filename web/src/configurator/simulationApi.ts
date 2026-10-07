/** Submission and job contract from the simulation API (PR #50). */
export interface SimulationSubmission {
  pdl: string
  roster: string
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

const API_BASE = (import.meta.env.VITE_SIMENV_API_BASE_URL || '/api').replace(/\/+$/, '')

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
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

async function requestJob(path: string, init: RequestInit, signal: AbortSignal): Promise<SimulationJob> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal.addEventListener('abort', abort, { once: true })
  if (signal.aborted) controller.abort()
  const timeout = window.setTimeout(abort, 15000)
  try {
    const response = await fetch(`${API_BASE}/simulations${path}`, { ...init, signal: controller.signal })
    const body: unknown = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(errorDetail(body) || `Simulation API request failed (HTTP ${response.status})`)
    }
    return parseJob(body)
  } catch (error) {
    if (signal.aborted) throw error
    if (controller.signal.aborted) throw new Error('Simulation API request timed out')
    if (error instanceof TypeError) throw new Error('Cannot reach the simulation API. Check the service and API URL.')
    throw error
  } finally {
    window.clearTimeout(timeout)
    signal.removeEventListener('abort', abort)
  }
}

export function submitSimulation(submission: SimulationSubmission, signal: AbortSignal) {
  return requestJob('', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(submission),
  }, signal)
}

export async function inspectSimulation(id: string, signal: AbortSignal) {
  const job = await requestJob(`/${encodeURIComponent(id)}`, {}, signal)
  if (job.id !== id) throw new Error('Invalid simulation API response: run ID changed')
  return job
}
