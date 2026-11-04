import type { PlaybackSource, RecordedFrame, RunSummary, Scene } from '../data/playback'
import { PlaybackApiError } from '../data/httpPlaybackSource'
import { getSimulationInputs, inspectSimulation, listSimulations, submitSimulation, SimulationApiError,
  type SimulationInputs, type SimulationJob, type SimulationSubmission } from '../configurator/simulationApi'
import { agentIdentity, referenceCompatibility, type RecordedReference } from './reference'

export const REFERENCE_LABEL = 'Automatic disruption-free reference'
export type FailureKind = 'discovery' | 'inputs' | 'rejected' | 'unknown-submission' | 'monitoring' | 'failed-job' | 'playback' | 'incompatible'
export interface PreparationState {
  phase: 'discovering' | 'submitting' | 'monitoring' | 'awaiting-playback' | 'ready' | 'error'
  reference?: RecordedReference
  jobId?: string
  progress?: number
  message: string
  failure?: FailureKind
}
export const INITIAL_PREPARATION: PreparationState = { phase: 'discovering', message: 'Finding a disruption-free reference…' }
export interface ReferenceEntry {
  getSnapshot(): PreparationState
  subscribe(listener: () => void): () => void
  retry(): void
}
interface ReferenceApi {
  inputs(id: string): Promise<SimulationInputs>
  list(limit: number, offset: number): Promise<{ items: SimulationJob[]; total: number }>
  submit(input: SimulationSubmission): Promise<SimulationJob>
  inspect(id: string): Promise<SimulationJob>
}
class PreparationFailure extends Error {
  constructor(public kind: FailureKind, message: string, public jobId?: string) { super(message) }
}
const message = (error: unknown) => error instanceof Error ? error.message : String(error)
const ineligible = (error: unknown) => (error instanceof SimulationApiError || error instanceof PlaybackApiError) && [404, 409].includes(error.status ?? 0)

export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (value && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => `${JSON.stringify(key)}:${canonical(child)}`).join(',')}}`
  return JSON.stringify(value)
}

export function referenceRecipe(inputs: SimulationInputs) {
  const scenario = inputs.pdl.scenario && typeof inputs.pdl.scenario === 'object' ? inputs.pdl.scenario : {}
  const pdl = { ...inputs.pdl, scenario: { ...scenario, name: REFERENCE_LABEL }, events: [],
    cascades: [{ id: 'unshocked_reference', timeline: [] }] }
  return { key: canonical({ pdl, roster: inputs.roster, parameters: inputs.parameters }),
    submission: { pdl: JSON.stringify(pdl), roster: inputs.roster === null ? null : JSON.stringify(inputs.roster),
      cascade: 'unshocked_reference', label: REFERENCE_LABEL } }
}

export function hasEmptyEvents(inputs: SimulationInputs): boolean {
  const events = inputs.pdl.events ?? []
  const cascades = inputs.pdl.cascades
  if (!Array.isArray(events) || events.length || !Array.isArray(cascades)) return false
  const selected = cascades.find(item => item && typeof item === 'object' && item.id === inputs.cascade)
  const timeline = selected?.timeline ?? []
  return !!selected && Array.isArray(timeline) && timeline.length === 0
}

function makeEntry(task: (publish: (state: PreparationState) => void) => Promise<void>): ReferenceEntry {
  let state = INITIAL_PREPARATION, running = false
  const listeners = new Set<() => void>()
  const publish = (next: PreparationState) => { state = next; listeners.forEach(listener => listener()) }
  return {
    getSnapshot: () => state,
    subscribe: listener => { listeners.add(listener); return () => { listeners.delete(listener) } },
    retry() {
      if (running) return
      running = true; publish(INITIAL_PREPARATION)
      void task(publish).then(() => { running = false }, error => {
        running = false
        publish({ phase: 'error', message: message(error),
          failure: error instanceof PreparationFailure ? error.kind : 'discovery',
          jobId: error instanceof PreparationFailure ? error.jobId : undefined,
        })
      })
    },
  }
}

/** Exhaust pagination: an outage or truncated history is not evidence of absence. */
async function allPages<T extends { id: string }>(load: (limit: number, offset: number) => Promise<{ items: T[]; total: number }>) {
  const result = new Map<string, T>()
  let offset = 0
  for (;;) {
    const page = await load(50, offset)
    const size = result.size
    page.items.forEach(item => result.set(item.id, item))
    offset += page.items.length
    if (page.items.length && result.size === size) throw new Error('Reference discovery history is incomplete')
    if (offset >= page.total) {
      if (result.size < page.total) throw new Error('Reference discovery history is incomplete')
      return [...result.values()]
    }
    if (!page.items.length) throw new Error('Reference discovery history is incomplete')
  }
}

export function createAutomaticReferenceCoordinator(source: PlaybackSource, api: ReferenceApi,
  options: { wait?: () => Promise<void>; maxPolls?: number } = {}) {
  const entries = new Map<string, ReferenceEntry>(), recipes = new Map<string, ReferenceEntry>()
  const wait = options.wait ?? (() => new Promise<void>(resolve => setTimeout(resolve, 1000)))
  const maxPolls = options.maxPolls ?? 600
  async function inputs(id: string) {
    try { return await api.inputs(id) }
    catch (error) { if (ineligible(error)) return null; throw error }
  }
  async function compatible(current: Scene, first: RecordedFrame, ref: RecordedReference) {
    try {
      const scene = await source.getScene(ref.runId, ref.scenarioId)
      if (referenceCompatibility(current, scene, ref.evidence)) return false
      const page = await source.getFrames(ref.runId, ref.scenarioId, current.min_period, 100)
      const initial = page.frames.find(frame => frame.period === current.min_period)
      if (!initial) throw new Error('Reference initial frame is missing')
      return canonical(first.agents.map(agentIdentity).sort()) === canonical(initial.agents.map(agentIdentity).sort())
    } catch (error) { if (ineligible(error)) return false; throw error }
  }
  return {
    ensure(runId: string, scenarioId: number): ReferenceEntry {
      const identity = canonical([runId, scenarioId])
      const existing = entries.get(identity)
      if (existing) return existing
      let delegate: ReferenceEntry | null = null
      const entry = makeEntry(async publish => {
        if (delegate) { delegate.retry(); return }
        if (source.mode !== 'recorded') throw new PreparationFailure('inputs', 'Static demo uses its explicitly labeled scenario-start comparison')
        const scene = await source.getScene(runId, scenarioId)
        const page = await source.getFrames(runId, scenarioId, scene.min_period, 100)
        const first = page.frames.find(frame => frame.period === scene.min_period)
        if (!first) throw new Error('Selected initial frame is missing')
        const runs = await allPages((limit, offset) => source.listRuns(limit, offset))
        const zeros = runs.filter(run => run.playable && run.scenario_ids.includes(0))
          .sort((a, b) => Number(b.id === runId) - Number(a.id === runId))
        for (const run of zeros) {
          const ref: RecordedReference = { runId: run.id, scenarioId: 0, evidence: 'scenario-zero' }
          if (await compatible(scene, first, ref)) { publish({ phase: 'ready', reference: ref, message: 'Recorded disruption-free reference ready' }); return }
        }
        const selected = await inputs(runId)
        if (!selected || selected.evidence !== 'execution-hashes') throw new PreparationFailure('inputs', 'Original verified inputs are unavailable for this recording. Select a recorded baseline or an explicit scenario-start comparison.')
        const recipe = referenceRecipe(selected)
        delegate = recipes.get(recipe.key) ?? null
        if (!delegate) {
          let jobId: string | undefined, unknown = false, failed = false
          const verified = async (id: string, completed: boolean) => {
            let value: SimulationInputs
            try { value = await api.inputs(id) }
            catch (error) { throw new PreparationFailure('monitoring', `Reference input verification failed: ${message(error)}`, id) }
            if (!hasEmptyEvents(value) || referenceRecipe(value).key !== recipe.key || (completed && value.evidence !== 'execution-hashes')) {
              throw new PreparationFailure('incompatible', 'Reference inputs or accepted scenario parameters do not match the selected experiment', id)
            }
          }
          delegate = makeEntry(async update => {
            if (failed) { jobId = undefined; failed = false }
            if (!jobId) {
              const candidates = await allPages((limit, offset) => source.listRuns(limit, offset))
              for (const run of candidates.filter(run => run.playable && run.scenario_ids.includes(0))
                .sort((a, b) => Number(b.id === runId) - Number(a.id === runId))) {
                const ref: RecordedReference = { runId: run.id, scenarioId: 0, evidence: 'scenario-zero' }
                if (await compatible(scene, first, ref)) { update({ phase: 'ready', reference: ref, message: 'Recorded disruption-free reference ready' }); return }
              }
              const rejected = new Set<string>()
              for (const run of candidates.filter(run => run.playable && run.scenario_ids.includes(1))) {
                const value = await inputs(run.id)
                if (!value || value.evidence !== 'execution-hashes' || !hasEmptyEvents(value) || referenceRecipe(value).key !== recipe.key) continue
                const ref: RecordedReference = { runId: run.id, scenarioId: 1, evidence: 'empty-events' }
                if (await compatible(scene, first, ref)) { update({ phase: 'ready', reference: ref, message: 'Verified disruption-free reference reused' }); return }
                rejected.add(run.id)
              }
              const history = await allPages((limit, offset) => api.list(limit, offset))
              const newest = await api.list(50, 0)
              // A queued job may finish between the two independent services'
              // discovery reads. Recheck playback before deciding to create.
              const refreshed = await allPages((limit, offset) => source.listRuns(limit, offset))
              for (const run of refreshed.filter(run => run.playable && run.scenario_ids.includes(0))
                .sort((a, b) => Number(b.id === runId) - Number(a.id === runId))) {
                const ref: RecordedReference = { runId: run.id, scenarioId: 0, evidence: 'scenario-zero' }
                if (await compatible(scene, first, ref)) { update({ phase: 'ready', reference: ref, message: 'Recorded disruption-free reference ready' }); return }
              }
              for (const job of [...new Map([...history, ...newest.items].map(job => [job.id, job])).values()]) {
                if (job.status === 'failed' || rejected.has(job.id)) continue
                const value = await inputs(job.id)
                if (!value || !hasEmptyEvents(value) || referenceRecipe(value).key !== recipe.key) continue
                if (job.status === 'completed') {
                  // Old completed history absent from this database is not a
                  // recorded reference; newly completed playable work is.
                  if (!refreshed.some(run => run.id === job.id && run.playable && run.scenario_ids.includes(1))) continue
                  const ref: RecordedReference = { runId: job.id, scenarioId: 1, evidence: 'empty-events' }
                  if (value.evidence === 'execution-hashes' && await compatible(scene, first, ref)) {
                    update({ phase: 'ready', reference: ref, message: 'Verified disruption-free reference reused' }); return
                  }
                  continue
                }
                jobId = job.id; break
              }
              if (!jobId) {
                if (unknown) throw new PreparationFailure('unknown-submission', 'Reference submission outcome is unknown. Retry discovery or inspect job history; no duplicate will be submitted.')
                const latest = await inputs(runId)
                if (!latest || referenceRecipe(latest).key !== recipe.key) throw new PreparationFailure('inputs', 'Selected preserved inputs are no longer available or consistent')
                if (canonical(latest.parameters) !== canonical(latest.current_parameters)) throw new PreparationFailure('inputs', 'Recorded parameters differ from current API defaults; this recording cannot be automatically reproduced')
                update({ phase: 'submitting', message: 'Submitting a separate disruption-free experiment…' })
                unknown = true
                try {
                  const job = await api.submit(recipe.submission)
                  jobId = job.id; unknown = false
                } catch (error) {
                  if (error instanceof SimulationApiError && !error.ambiguous) unknown = false
                  throw new PreparationFailure(unknown ? 'unknown-submission' : 'rejected', message(error))
                }
              }
              await verified(jobId, false)
            }
            for (let poll = 0; poll < maxPolls; poll++) {
              let job: SimulationJob
              try { job = await api.inspect(jobId) }
              catch (error) { throw new PreparationFailure('monitoring', `Reference monitoring paused: ${message(error)}`, jobId) }
              if (job.status === 'failed') {
                failed = true
                throw new PreparationFailure('failed-job', `Reference experiment failed: ${job.error || 'unknown error'}. Retry to request a replacement.`, jobId)
              }
              if (job.status === 'completed') {
                await verified(jobId, true)
                update({ phase: 'awaiting-playback', jobId, message: 'Reference completed; awaiting playback availability…' })
                for (let attempt = 0; attempt < maxPolls; attempt++) {
                  let recorded: RunSummary[]
                  try { recorded = await allPages((limit, offset) => source.listRuns(limit, offset)) }
                  catch (error) { throw new PreparationFailure('playback', `Reference playback discovery failed: ${message(error)}`, jobId) }
                  const match = recorded.find(run => run.id === jobId && run.playable && run.scenario_ids.includes(1))
                  if (match) {
                    const ref: RecordedReference = { runId: jobId, scenarioId: 1, evidence: 'empty-events' }
                    if (!await compatible(scene, first, ref)) throw new PreparationFailure('incompatible', 'Completed reference has incompatible structure, periods or agent identities', jobId)
                    update({ phase: 'ready', reference: ref, jobId, message: 'Verified disruption-free reference ready' }); return
                  }
                  await wait()
                }
                throw new PreparationFailure('playback', 'Reference is not yet visible in the configured playback database; retry without resubmitting', jobId)
              }
              update({ phase: 'monitoring', jobId, progress: job.progress.percent_complete,
                message: `Disruption-free reference ${job.status}: ${job.progress.percent_complete.toFixed(1)}%` })
              await wait()
            }
            throw new PreparationFailure('monitoring', 'Reference monitoring timed out; retry monitoring the accepted job', jobId)
          })
          recipes.set(recipe.key, delegate) // Publish ownership before any async work.
          delegate.retry()
        }
        const shared = delegate
        shared.subscribe(() => publish(shared.getSnapshot()))
        publish(shared.getSnapshot())
      })
      const retry = entry.retry.bind(entry)
      const result = { ...entry, retry: () => delegate ? delegate.retry() : retry() }
      entries.set(identity, result)
      retry()
      return result
    },
  }
}

const coordinators = new WeakMap<PlaybackSource, ReturnType<typeof createAutomaticReferenceCoordinator>>()
export function automaticReferenceCoordinator(source: PlaybackSource) {
  let coordinator = coordinators.get(source)
  if (!coordinator) {
    const signal = () => new AbortController().signal
    coordinator = createAutomaticReferenceCoordinator(source, {
      inputs: id => getSimulationInputs(id, signal()),
      list: (limit, offset) => listSimulations(limit, offset, signal()),
      submit: input => submitSimulation(input, signal()), inspect: id => inspectSimulation(id, signal()),
    })
    coordinators.set(source, coordinator)
  }
  return coordinator
}
