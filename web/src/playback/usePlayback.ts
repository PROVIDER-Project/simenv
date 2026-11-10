import { useCallback, useEffect, useMemo, useState } from 'react'
import type { PlaybackSource, RecordedFrame, Scene } from '../data/playback'
import { createPlaybackBuffer } from './buffer'
import { createReferenceLoader, referenceExplanation, type ReferenceResult } from './referenceLoader'
import type { ReferenceChoice } from './reference'

interface CurrentResource {
  key: object
  scene: Scene
  baseline: RecordedFrame
  cache: ReturnType<typeof createPlaybackBuffer>
}
interface Snapshot { key: object; selection: object; frame: RecordedFrame; reference: ReferenceResult }
interface Failure { key: object; message: string }
const message = (error: unknown) => error instanceof Error ? error.message : String(error)

/** Current/reference measurements are committed as one coherent display snapshot. */
export function usePlayback(source: PlaybackSource, runId: string, scenarioId: number, choice: ReferenceChoice = 'start') {
  const [initialRetry, setInitialRetry] = useState(0)
  const [referenceRetry, setReferenceRetry] = useState(0)
  const [retry, setRetry] = useState(0)
  const selection = useMemo(() => ({ source, runId, scenarioId, initialRetry }), [source, runId, scenarioId, initialRetry])
  const generation = useMemo(() => ({ selection, choice, referenceRetry }), [selection, choice, referenceRetry])
  const [current, setCurrent] = useState<CurrentResource | null>(null)
  const [resource, setResource] = useState<{ key: object; loader: ReturnType<typeof createReferenceLoader> } | null>(null)
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [pending, setPending] = useState<object | null>(null)
  const [initialError, setInitialError] = useState<Failure | null>(null)
  const [loadError, setLoadError] = useState<Failure | null>(null)
  const [target, setTarget] = useState(0)
  const [playing, setPlaying] = useState(false)
  const active = current?.key === selection ? current : null

  useEffect(() => {
    const controller = new AbortController()
    const cache = createPlaybackBuffer(source, runId, scenarioId)
    source.getScene(runId, scenarioId, controller.signal).then(async scene => {
      const baseline = await cache.load(scene.min_period)
      if (controller.signal.aborted) return
      setCurrent({ key: selection, scene, baseline, cache })
      setTarget(baseline.period); setPlaying(scene.max_period > scene.min_period)
    }).catch(error => {
      if (!controller.signal.aborted) setInitialError({ key: selection, message: message(error) })
    })
    return () => { controller.abort(); cache.dispose() }
  }, [source, runId, scenarioId, selection])

  useEffect(() => {
    if (!active || choice === null) return
    const loader = createReferenceLoader(source, active.scene, active.baseline, choice)
    setResource({ key: generation, loader })
    return () => loader.dispose()
  }, [source, active, choice, generation])

  useEffect(() => {
    if (!active || resource?.key !== generation) return
    const controller = new AbortController()
    const cache = active.cache
    const loader = resource.loader
    const cached = active.cache.peek(target)
    // A cache hit is not a loading state, but load() still refreshes LRU/protection.
    if (!cached || !resource.loader.peek(cached)) setPending(generation)
    setLoadError(null)
    async function load() {
      const frame = await cache.load(target)
      if (controller.signal.aborted) return
      const reference = await loader.load(frame, controller.signal)
      if (controller.signal.aborted) return
      setSnapshot({ key: generation, selection, frame, reference })
      setPending(null)
    }
    void load().catch(error => {
      if (!controller.signal.aborted) {
        setLoadError({ key: generation, message: message(error) })
        setPending(null); setPlaying(false)
      }
    })
    return () => controller.abort()
  }, [active, resource, generation, selection, target, retry])

  const valid = snapshot?.key === generation ? snapshot : null
  const frame = snapshot?.selection === selection ? snapshot.frame : active?.baseline ?? null
  const error = initialError?.key === selection ? initialError.message : loadError?.key === generation ? loadError.message : null
  const buffering = !error && (!valid || pending === generation)
  const referenceFrame = valid?.reference.frame ?? null

  useEffect(() => {
    if (!playing || !valid || !active || buffering || error || valid.frame.period !== target) return
    const period = valid.frame.period
    const next = period >= active.scene.max_period ? active.scene.min_period : period + 1
    const nextPage = (Math.floor(period / 100) + 1) * 100
    if (nextPage <= active.scene.max_period) {
      active.cache.prefetch(nextPage)
      resource?.loader.prefetch(nextPage)
    }
    const timer = window.setTimeout(() => setTarget(next), 60)
    return () => window.clearTimeout(timer)
  }, [playing, valid, active, buffering, error, target, resource])

  const seek = useCallback((period: number) => {
    setPlaying(false); setTarget(period); setRetry(value => value + 1)
  }, [])
  return { scene: active?.scene ?? null, baseline: active?.baseline ?? null, frame, playing, buffering, error, seek,
    retryPlayback: () => active ? setRetry(value => value + 1) : setInitialRetry(value => value + 1),
    toggle: () => setPlaying(value => !value),
    reference: { frame: referenceFrame, loading: buffering,
      error: valid?.reference.error ?? null,
      explanation: referenceExplanation(active?.scene ?? null, frame, referenceFrame, active?.baseline ?? null, choice),
      retry: () => setReferenceRetry(value => value + 1) } }
}
