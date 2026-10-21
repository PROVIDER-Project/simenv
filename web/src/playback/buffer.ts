import type { FramePage, PlaybackSource, RecordedFrame } from '../data/playback'
import { measure } from './measure'

/** A bounded cache for one selection. dispose invalidates even uncancellable requests. */
export function createPlaybackBuffer(source: Pick<PlaybackSource, 'getFrames'>, run: string, scenario: number) {
  const pages = new Map<number, FramePage>()
  const pending = new Map<number, Promise<FramePage>>()
  const controller = new AbortController()
  let current = 0
  const aligned = (period: number) => Math.floor(period / 100) * 100
  function evict() {
    while (pages.size > 3) {
      const oldest = [...pages.keys()].find(key => key !== current)
      if (oldest === undefined) break
      pages.delete(oldest)
    }
  }
  async function pageAt(start: number): Promise<FramePage> {
    if (controller.signal.aborted) throw new DOMException('Selection changed', 'AbortError')
    const cached = pages.get(start)
    if (cached) { pages.delete(start); pages.set(start, cached); return cached }
    const existing = pending.get(start)
    if (existing) return existing
    const request = source.getFrames(run, scenario, start, 100, controller.signal).then(page => {
      if (controller.signal.aborted) throw new DOMException('Selection changed', 'AbortError')
      const begin = performance.now()
      pages.set(start, page); evict()
      measure('playback.cache', begin)
      return page
    }).finally(() => pending.delete(start))
    pending.set(start, request)
    return request
  }
  return {
    async load(period: number): Promise<RecordedFrame> {
      current = aligned(period)
      const page = await pageAt(current)
      const frame = page.frames[period - page.start]
      if (!frame || frame.period !== period) throw new Error('Recorded frame missing')
      return frame
    },
    prefetch(period: number) { void pageAt(aligned(period)).catch(() => { /* load surfaces retryable errors */ }) },
    dispose() { controller.abort(); pages.clear(); pending.clear() },
  }
}
