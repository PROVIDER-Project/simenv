import { useEffect, useMemo, useState } from 'react'
import type { PlaybackSource, RecordedFrame, Scene } from '../data/playback'
import { createPlaybackBuffer } from './buffer'
import { agentIdentity, referenceCompatibility } from './reference'

type Buffer = ReturnType<typeof createPlaybackBuffer>
interface Resource { key: object; cache: Buffer; scene: Scene }
interface Loaded { key: object; period: number; frame: RecordedFrame | null; error: string | null }
const message = (error: unknown) => error instanceof Error ? error.message : String(error)
const identities = (frame: RecordedFrame) => JSON.stringify(frame.agents.map(agentIdentity).sort())

/** Reference failure never stops playback or silently changes reference modes. */
export function useReference(source: PlaybackSource, scene: Scene | null, frame: RecordedFrame | null,
  baseline: RecordedFrame | null, choice: string) {
  const [resource, setResource] = useState<Resource | null>(null)
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [setupError, setSetupError] = useState<{ key: object; message: string } | null>(null)
  const [retry, setRetry] = useState(0)
  // A fresh identity even when returning to a previously selected run. Never
  // resurrect errors/results/resources from a disposed selection lifecycle.
  const key = useMemo(() => ({ scene, choice, retry, baseline }), [scene, choice, retry, baseline])

  useEffect(() => {
    if (!scene || !baseline || choice === 'start') return
    const controller = new AbortController()
    const cache = createPlaybackBuffer(source, choice, 0)
    source.getScene(choice, 0, controller.signal).then(async referenceScene => {
      if (controller.signal.aborted) return
      const error = referenceCompatibility(scene, referenceScene)
      if (error) throw new Error(error)
      const first = await cache.load(scene.min_period)
      if (controller.signal.aborted) return
      if (identities(first) !== identities(baseline)) throw new Error('Reference agent identities are incompatible with the selected scenario start')
      setResource({ key, cache, scene: referenceScene })
    }).catch(error => {
      if (!controller.signal.aborted) setSetupError({ key, message: message(error) })
    })
    return () => { controller.abort(); cache.dispose() }
  }, [source, scene, choice, key, baseline])

  const period = frame?.period
  useEffect(() => {
    if (!resource || resource.key !== key || period === undefined) return
    let cancelled = false
    resource.cache.load(period).then(reference => {
      if (!cancelled) setLoaded({ key, period, frame: reference, error: null })
    }).catch(error => {
      if (!cancelled) setLoaded({ key, period, frame: null, error: message(error) })
    })
    return () => { cancelled = true }
  }, [resource, key, period])

  const start = choice === 'start'
  const candidate = start ? baseline : loaded?.key === key && loaded.period === period ? loaded.frame : null
  const error = start ? null : setupError?.key === key ? setupError.message : loaded?.key === key && loaded.period === period ? loaded.error : null
  // A disappearing agent is missing evidence, not grounds to discard valid
  // comparisons for every other agent/node. Projection joins exact keys only.
  const warning = candidate && frame && identities(candidate) !== identities(frame)
    ? ' Recorded agent identities differ at this period; only exact matches are compared. Missing agents are unavailable evidence.' : ''
  const reference = error ? null : candidate
  const loading = !start && !reference && !error
  const explanation = (start
    ? `Relative to scenario start (first recorded step ${baseline?.period ?? '…'}). This cannot reveal disturbances already present at the first step.`
    : `Recorded unshocked reference: ${choice}, scenario 0, corresponding step ${period ?? '…'}.${choice !== scene?.run_id ? ' Structurally compatible baseline; economic configuration equivalence is not verified.' : ''}`) + warning
  return { frame: reference, explanation, loading, error, retry: () => setRetry(value => value + 1) }
}
