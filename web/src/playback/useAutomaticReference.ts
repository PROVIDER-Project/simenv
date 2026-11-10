import { useEffect, useMemo, useState } from 'react'
import type { PlaybackSource } from '../data/playback'
import { automaticReferenceCoordinator, INITIAL_PREPARATION, type PreparationState, type ReferenceEntry } from './automaticReference'

/** UI subscriptions never own or cancel an already accepted reference job. */
export function useAutomaticReference(source: PlaybackSource, run: string, scenario: number, enabled: boolean) {
  const key = useMemo(() => ({ source, run, scenario, enabled }), [source, run, scenario, enabled])
  const [value, setValue] = useState<{ key: object; entry: ReferenceEntry; state: PreparationState } | null>(null)
  useEffect(() => {
    if (!enabled || source.mode !== 'recorded') return
    const entry = automaticReferenceCoordinator(source).ensure(run, scenario)
    const update = () => setValue({ key, entry, state: entry.getSnapshot() })
    const unsubscribe = entry.subscribe(update)
    update()
    return unsubscribe
  }, [source, run, scenario, enabled, key])
  const active = value?.key === key ? value : null
  return { ...(active?.state ?? INITIAL_PREPARATION), retry: () => active?.entry.retry() }
}
