import { createContext, useContext, useEffect } from 'react'
import type { Panel } from './steps'

export type TutorialAction = 'execution' | 'results'
const noop = () => {}
export const TutorialContext = createContext<{
  panel?: Panel
  entry: number
  completeAction?: (action: TutorialAction) => void
}>({ entry: 0 })

/** Capture the current step entry for completion of an action started now. */
export function useTutorialAction(action: TutorialAction): () => void {
  const { completeAction } = useContext(TutorialContext)
  return completeAction ? () => completeAction(action) : noop
}

/** Reveal only on step entry (or panel mount), never on playback updates. */
export function useTutorialPanel(panel: Panel, reveal: () => void | (() => void)) {
  const request = useContext(TutorialContext)
  useEffect(() => {
    if (request.panel === panel) return reveal()
  }, [request.panel, request.entry, panel, reveal])
}
