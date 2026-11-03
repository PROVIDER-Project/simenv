import type { PlaybackSource, RecordedFrame, Scene } from '../data/playback'
import { createPlaybackBuffer } from './buffer'
import { agentIdentity, referenceCompatibility } from './reference'

export interface ReferenceResult { frame: RecordedFrame | null; error: string | null }
const identities = (frame: RecordedFrame) => JSON.stringify(frame.agents.map(agentIdentity).sort())

/** One reference generation. Failures settle until an explicit retry replaces it. */
export function createReferenceLoader(source: PlaybackSource, scene: Scene, baseline: RecordedFrame, choice: string) {
  const controller = new AbortController()
  const cache = createPlaybackBuffer(source, choice, 0)
  const start = choice === 'start'
  let ready = start
  let failure: string | null = null
  let setup: Promise<void> | null = null
  function active(signal?: AbortSignal) {
    if (controller.signal.aborted || signal?.aborted) throw new DOMException('Reference changed', 'AbortError')
  }
  async function initialize() {
    const reference = await source.getScene(choice, 0, controller.signal)
    active()
    const error = referenceCompatibility(scene, reference)
    if (error) throw new Error(error)
    const first = await cache.load(scene.min_period)
    active()
    if (identities(first) !== identities(baseline)) throw new Error('Reference agent identities are incompatible with the selected scenario start')
    ready = true
  }
  return {
    peek(current: RecordedFrame): ReferenceResult | null {
      if (controller.signal.aborted) return null
      if (failure) return { frame: null, error: failure }
      if (start) return { frame: baseline, error: null }
      const frame = ready ? cache.peek(current.period) : null
      return frame ? { frame, error: null } : null
    },
    async load(current: RecordedFrame, signal?: AbortSignal): Promise<ReferenceResult> {
      active(signal)
      if (failure) return { frame: null, error: failure }
      if (start) return { frame: baseline, error: null }
      try {
        await (setup ??= initialize())
        active(signal)
        const frame = await cache.load(current.period)
        active(signal)
        return { frame, error: null }
      } catch (error) {
        active(signal) // Disposed or superseded work never latches a failure.
        failure = error instanceof Error ? error.message : String(error)
        return { frame: null, error: failure }
      }
    },
    prefetch(period: number) { if (ready && !start && !failure) cache.prefetch(period) },
    dispose() { controller.abort(); cache.dispose() },
  }
}

export function referenceExplanation(scene: Scene | null, current: RecordedFrame | null, reference: RecordedFrame | null,
  baseline: RecordedFrame | null, choice: string): string {
  const source = choice === 'start'
    ? `Relative to scenario start (first recorded step ${baseline?.period ?? '…'}). This cannot reveal disturbances already present at the first step.`
    : `Recorded unshocked reference: ${choice}, scenario 0, corresponding recorded periods.${choice !== scene?.run_id ? ' Structurally compatible baseline; economic configuration equivalence is not verified.' : ''}`
  return source + (reference && current && identities(reference) !== identities(current)
    ? ' Recorded agent identities differ at this period; only exact matches are compared. Missing agents are unavailable evidence.' : '')
}
