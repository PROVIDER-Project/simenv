import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { TutorialContext, type TutorialAction } from './context'
import { steps, type Language } from './steps'
import './tutorial.css'

const prefix = 'simenv.tutorial.v1.'
function read(key: string) { try { return localStorage.getItem(prefix + key) } catch { return null } }
function write(key: string, value?: string) { try { if (value) localStorage.setItem(prefix + key, value); else localStorage.removeItem(prefix + key) } catch { /* Storage is optional. */ } }
type Rect = { x: number; y: number; width: number; height: number }

export default function Tutorial({ children, mode, layoutReady }: { children: (restartNode: ReactNode) => ReactNode; mode: 'static' | 'recorded'; layoutReady: boolean }) {
  const [{ active, index, entry }, setTour] = useState(() => ({ active: read('completed') !== 'true', index: 0, entry: 0 }))
  const [language, setLanguage] = useState<Language>(() => read('language') === 'de' ? 'de' : 'en')
  const [target, setTarget] = useState<Rect | null>(null)
  const [position, setPosition] = useState({ left: 8, top: 8 })
  const [dockHeight, setDockHeight] = useState<number | null>(null)
  const popover = useRef<HTMLElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const restart = useRef<HTMLButtonElement>(null)
  const opener = useRef<HTMLElement | null>(null)
  const step = steps[index]
  const de = language === 'de'
  const close = useCallback(() => {
    setTour(current => ({ ...current, active: false, entry: current.entry + 1 }))
    const element = opener.current
    ;(element?.isConnected ? element : restart.current)?.focus({ preventScroll: true })
  }, [])
  useEffect(() => {
    if (!active) return
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.preventDefault(); close() } }
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [active, close])

  useLayoutEffect(() => {
    if (!active) return
    heading.current?.focus({ preventScroll: true })
  }, [active, step, entry])

  useLayoutEffect(() => {
    if (!active) return
    let revealed = false
    let docked = false
    let dockRevealPending = false
    let recoverVisibility = false
    let wasAccessible = false
    let frame = 0
    let observed: Element | null = null
    setDockHeight(null)
    const resize = new ResizeObserver(() => schedule())
    function accessible(element: HTMLElement) {
      const rect = element.getBoundingClientRect()
      let top = 0, bottom = window.innerHeight, left = 0, right = window.innerWidth
      for (let parent = element.parentElement; parent; parent = parent.parentElement) {
        const style = getComputedStyle(parent)
        const bounds = parent.getBoundingClientRect()
        if (style.overflowY !== 'visible') {
          top = Math.max(top, bounds.top + parent.clientTop)
          bottom = Math.min(bottom, bounds.top + parent.clientTop + parent.clientHeight)
        }
        if (style.overflowX !== 'visible') {
          left = Math.max(left, bounds.left + parent.clientLeft)
          right = Math.min(right, bounds.left + parent.clientLeft + parent.clientWidth)
        }
      }
      return rect.top >= top - 1 && rect.bottom <= bottom + 1 && rect.left >= left - 1 && rect.right <= right + 1
    }
    function update() {
      // Another animation frame can run before React commits the dock styles.
      // Keep its one-time reveal pending until the docked layout is in the DOM.
      if (dockRevealPending && popover.current?.closest('.sim-tutorial-shell--docked')) {
        recoverVisibility = true
        dockRevealPending = false
      }
      const element = document.querySelector<HTMLElement>(`[data-tutorial="${step.id}"]`)
      const visible = element && element.getClientRects().length > 0 && !element.closest('[hidden]')
      let justRevealed = false
      if (visible && layoutReady && (!revealed || (recoverVisibility && !accessible(element)))) {
        // Initial asynchronous playback panels precede the configurator in
        // mobile flow. Reveal only after that initial layout has mounted.
        revealed = true
        justRevealed = true
        element.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' })
      }
      recoverVisibility = false
      wasAccessible = !!visible && accessible(element)
      if (element !== observed) { if (observed) resize.unobserve(observed); observed = element; if (element) resize.observe(element) }
      const bounds = visible ? element.getBoundingClientRect() : null
      const rect = bounds ? { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height } : null
      setTarget(previous => JSON.stringify(previous) === JSON.stringify(rect) ? previous : rect)
      const width = popover.current?.offsetWidth ?? 340
      const height = popover.current?.offsetHeight ?? 280
      const vw = window.innerWidth, vh = window.innerHeight
      if (docked) {
        const space = height + 16
        setDockHeight(previous => previous === space ? previous : space)
        setPosition(previous => previous.left === 8 && previous.top === 8 ? previous : { left: 8, top: 8 })
        return
      }
      const clampX = (x: number) => Math.max(8, Math.min(x, vw - width - 8))
      const clampY = (y: number) => Math.max(8, Math.min(y, vh - height - 8))
      const candidates = rect ? [
        { left: rect.x - width - 16, top: clampY(rect.y) },
        { left: rect.x + rect.width + 16, top: clampY(rect.y) },
        { left: clampX(rect.x), top: rect.y + rect.height + 12 },
        { left: clampX(rect.x), top: rect.y - height - 12 },
      ] : []
      const fits = candidates.find(p => p.left >= 8 && p.top >= 8 && p.left + width <= vw - 8 && p.top + height <= vh - 8)
      if (rect && !fits && layoutReady && (justRevealed || wasAccessible)) {
        // A clamped floating card can cover every control on a short screen.
        // Dock instead, reserving actual application space. Keep this choice
        // for this step/viewport so scrolling cannot oscillate between layouts.
        docked = true
        dockRevealPending = true
        setDockHeight(Math.min(vh * .42, 240) + 16)
        schedule()
        return
      }
      const next = fits ?? { left: clampX((vw - width) / 2), top: clampY(rect && rect.y < vh / 2 ? vh - height - 8 : 8) }
      setPosition(previous => previous.left === next.left && previous.top === next.top ? previous : next)
    }
    function schedule() { cancelAnimationFrame(frame); frame = requestAnimationFrame(update) }
    function viewportResize() {
      // Do not undo a deliberate scroll away from the target. Only recover a
      // target that the viewport change itself made inaccessible; never open
      // a panel that the user has since collapsed.
      recoverVisibility = wasAccessible
      // A dock chosen for mobile flow must not shrink a newly active desktop
      // grid. Re-evaluate against the new viewport without a reserved inset;
      // scroll, playback and element-size observers never reset this latch.
      docked = false
      dockRevealPending = false
      setDockHeight(null)
      schedule()
    }
    const mutations = new MutationObserver(schedule)
    mutations.observe(document.getElementById('root')!, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'class'] })
    if (popover.current) resize.observe(popover.current)
    document.addEventListener('scroll', schedule, true)
    window.addEventListener('resize', viewportResize)
    schedule()
    return () => { cancelAnimationFrame(frame); resize.disconnect(); mutations.disconnect(); document.removeEventListener('scroll', schedule, true); window.removeEventListener('resize', viewportResize) }
  }, [active, step, entry, layoutReady])

  function move(next: number) { setTour(current => ({ ...current, index: next, entry: current.entry + 1 })) }
  function completeAction(action: TutorialAction) {
    if (!active || step.id !== action) return
    setTour(current => current.active && steps[current.index].id === action && current.entry === entry
      ? { active: true, index: current.index + 1, entry: current.entry + 1 }
      : current)
  }
  return <TutorialContext.Provider value={{ panel: active ? step.panel : undefined, entry, completeAction }}>
    <div className={active && dockHeight !== null ? 'sim-tutorial-shell sim-tutorial-shell--docked' : 'sim-tutorial-shell'} style={{ '--sim-tutorial-space': `${dockHeight ?? 0}px` } as CSSProperties}>
    {children(<button className="sim-tutorial-restart" ref={restart} type="button" onClick={() => {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      write('completed'); setTour(current => ({ active: true, index: 0, entry: current.entry + 1 }))
    }}>Restart tutorial</button>)}
    {active && <>
      {target && <div className="sim-tutorial-highlight" aria-hidden="true" style={{ left: target.x - 4, top: target.y - 4, width: target.width + 8, height: target.height + 8 }} />}
      <section ref={popover} className="sim-tutorial" data-step={step.id} role="region" aria-label="Interactive tutorial" lang={language} style={position}>
        <div className="sim-tutorial-bar"><span>{index + 1} / {steps.length}</span><div>
          <button type="button" aria-pressed={!de} onClick={() => { setLanguage('en'); write('language', 'en') }}>English</button>
          <button type="button" aria-pressed={de} onClick={() => { setLanguage('de'); write('language', 'de') }}>Deutsch</button>
        </div></div>
        <h2 ref={heading} tabIndex={-1}>{step[language][0]}</h2>
        <p>{step[language][1]}</p>
        {step.id === 'runs' && <p>{mode === 'static'
          ? (de ? 'Statische Demo: keine Verbindung zu eingereichten Läufen. Für eigene Ergebnisse ist die aufgezeichnete Wiedergabe erforderlich.' : 'Static demo: separate from submitted runs. Recorded playback must be configured to view your own results.')
          : (de ? 'Aufgezeichneter Modus: Daten stammen aus dem ausgewählten Datenbanklauf.' : 'Recorded mode: data comes from the selected database run.')}</p>}
        {!target && <p role="status">{de ? 'Dieser Bereich ist noch nicht verfügbar. Du kannst weitergehen oder zurückkehren, sobald die Daten bereit sind.' : 'This area is not available yet. Continue freely or return when its data is ready.'}</p>}
        <div className="sim-tutorial-actions">
          <button type="button" onClick={close}>{de ? 'Schließen (Sitzung)' : 'Close for session'}</button>
          <button type="button" disabled={!index} onClick={() => move(index - 1)}>{de ? 'Zurück' : 'Back'}</button>
          {index < steps.length - 1 ? <button type="button" onClick={() => move(index + 1)}>{de ? 'Weiter' : 'Next'}</button>
            : <button type="button" onClick={() => { write('completed', 'true'); close() }}>{de ? 'Abschließen' : 'Finish'}</button>}
        </div>
      </section>
    </>}
    </div>
  </TutorialContext.Provider>
}
