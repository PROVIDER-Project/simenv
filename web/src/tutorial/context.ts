import { createContext, useContext, useEffect } from 'react'
import type { Panel } from './steps'

export const TutorialContext = createContext<{ panel?: Panel; entry: number }>({ entry: 0 })

/** Reveal only on step entry (or panel mount), never on playback updates. */
export function useTutorialPanel(panel: Panel, reveal: () => void) {
  const request = useContext(TutorialContext)
  useEffect(() => {
    if (request.panel === panel) reveal()
  }, [request.panel, request.entry, panel, reveal])
}
