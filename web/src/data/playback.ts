import type { Node, Edge } from './types'

export interface RunSummary {
  id: string
  label: string | null
  started_at: string
  finished_at: string | null
  status: string
  scenario_ids: number[]
  period_num: number
  playable: boolean
  unavailable_reason: string | null
}
export interface RunList { items: RunSummary[]; total: number }
export interface Scene {
  run_id: string
  scenario_id: number
  min_period: number
  max_period: number
  pdl: string
  honesty_note: string
  nodes: Node[]
  edges: Edge[]
}
export interface AgentState {
  entity_id: string
  agent_id: number
  role: string
  values: Record<string, number>
}
export interface RecordedFrame { period: number; agents: AgentState[] }
export interface FramePage {
  run_id: string
  scenario_id: number
  start: number
  next_start: number | null
  frames: RecordedFrame[]
}
export interface PlaybackSource {
  name: string
  listRuns(limit: number, offset: number, signal?: AbortSignal): Promise<RunList>
  getScene(runId: string, scenarioId: number, signal?: AbortSignal): Promise<Scene>
  getFrames(runId: string, scenarioId: number, start: number, limit: number, signal?: AbortSignal): Promise<FramePage>
}
