import { useCallback, useEffect, useRef, useState } from 'react'
import type { PlaybackSource, RecordedFrame, Scene } from '../data/playback'
import { createPlaybackBuffer } from './buffer'

/** Mounted once per run/scenario; the parent keys this hook's owner by selection. */
export function usePlayback(source: PlaybackSource, runId: string, scenarioId: number) {
  const [scene, setScene] = useState<Scene | null>(null)
  const [baseline, setBaseline] = useState<RecordedFrame | null>(null)
  const [frame, setFrame] = useState<RecordedFrame | null>(null)
  const [target, setTarget] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [buffering, setBuffering] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const buffer = useRef<ReturnType<typeof createPlaybackBuffer> | null>(null)
  const [initialRetry, setInitialRetry] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const cache = createPlaybackBuffer(source, runId, scenarioId)
    buffer.current = cache
    setBuffering(true); setError(null)
    Promise.all([source.getScene(runId, scenarioId, controller.signal), cache.load(0)])
      .then(([nextScene, first]) => {
        if (controller.signal.aborted) return
        setScene(nextScene); setBaseline(first); setFrame(first)
        setBuffering(false); setPlaying(nextScene.max_period > 0)
      }).catch(reason => {
        if (!controller.signal.aborted) { setError(String(reason instanceof Error ? reason.message : reason)); setBuffering(false) }
      })
    return () => { controller.abort(); cache.dispose(); buffer.current = null }
  }, [source, runId, scenarioId, initialRetry])

  useEffect(() => {
    if (!scene || !baseline || !buffer.current) return
    let cancelled = false
    setBuffering(true); setError(null)
    const cache = buffer.current
    cache.load(target).then(next => {
      if (cancelled) return
      setFrame(next); setBuffering(false)
    }).catch(reason => {
      if (!cancelled) {
        setError(reason instanceof Error ? reason.message : String(reason))
        setBuffering(false); setPlaying(false)
      }
    })
    return () => { cancelled = true }
  }, [target, scene, baseline, retry])

  useEffect(() => {
    if (!playing || !frame || !scene || buffering || error) return
    const next = frame.period >= scene.max_period ? 0 : frame.period + 1
    const nextPage = (Math.floor(frame.period / 100) + 1) * 100
    if (nextPage <= scene.max_period) buffer.current?.prefetch(nextPage)
    const timer = window.setTimeout(() => setTarget(next), 60)
    return () => window.clearTimeout(timer)
  }, [playing, frame, scene, buffering, error])

  const seek = useCallback((period: number) => {
    setPlaying(false); setTarget(period); setRetry(value => value + 1)
  }, [])
  const retryPlayback = () => scene ? setRetry(value => value + 1) : setInitialRetry(value => value + 1)
  return { scene, baseline, frame, playing, buffering, error, seek, retryPlayback,
    toggle: () => setPlaying(value => !value) }
}
