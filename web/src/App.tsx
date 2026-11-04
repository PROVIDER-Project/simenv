import { Profiler, useCallback, useEffect, useId, useMemo, useRef, useState, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import type { PlaybackSource, RunSummary } from './data/playback'
import { resolveScene } from './data/gazetteer'
import { presentScene } from './data/presentation'
import { designVars } from './design/tokens'
import GlobeView from './globe/GlobeView'
import ScenarioConfigurator from './configurator/ScenarioConfigurator'
import Timeline from './playback/Timeline'
import RunSelector from './playback/RunSelector'
import { usePlayback } from './playback/usePlayback'
import { projectFrame } from './playback/frame'
import { measure } from './playback/measure'
import ReferenceSelector from './playback/ReferenceSelector'
import StatusPanel, { StatusLegend } from './playback/StatusPanel'
import StableInspector from './playback/StableInspector'
import { useAutomaticReference } from './playback/useAutomaticReference'
import { REFERENCE_LABEL } from './playback/automaticReference'
import './app.css'
import './playback/status.css'

export default function App({ source }: { source: PlaybackSource }) {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [total, setTotal] = useState(0)
  const [selected, setSelected] = useState('')
  const [scenario, setScenario] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [offset, setOffset] = useState(0)
  const [nextOffset, setNextOffset] = useState(0)
  const [impactSlot, setImpactSlot] = useState<HTMLDivElement | null>(null)
  const selection = useRef('')
  const opening = useRef<AbortController | null>(null)
  const refreshRuns = useCallback(() => { setOffset(0); setRefresh(value => value + 1) }, [])
  useEffect(() => () => opening.current?.abort(), [])

  const viewResults = useCallback(async (runId: string): Promise<void> => {
    if (source.mode === 'static') throw new Error('Viewing submitted results requires recorded playback. Configure VITE_PLAYBACK_API_BASE_URL; the displayed static demo is separate from your submitted run.')
    opening.current?.abort()
    const controller = new AbortController()
    opening.current = controller
    try {
      let offset = 0
      let found: RunSummary | undefined
      while (!found) {
        const page = await source.listRuns(50, offset, controller.signal)
        if (controller.signal.aborted) throw new Error('Results selection changed')
        found = page.items.find(item => item.id === runId)
        offset += page.items.length
        if (found || !page.items.length || offset >= page.total) break
      }
      if (!found) throw new Error(`Run ${runId} is not in the configured playback database. Check both services use the same database, then retry View results.`)
      if (!found.playable || !found.scenario_ids.includes(1)) throw new Error(found.unavailable_reason || 'This completed run does not have playable scenario 1 results yet. Retry View results.')
      if (controller.signal.aborted) throw new Error('Results selection changed')
      selection.current = runId
      setRuns(current => [...current.filter(item => item.id !== runId), found])
      setSelected(runId); setScenario(1)
    } finally {
      if (opening.current === controller) opening.current = null
    }
  }, [source])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(null)
    async function load() {
      let page = await source.listRuns(50, offset, controller.signal)
      const loaded = [...page.items]
      // Initial discovery can pass unavailable runs without loading all measurements.
      while (!selection.current && !loaded.some(run => run.playable) && loaded.length + offset < page.total && page.items.length) {
        page = await source.listRuns(50, offset + loaded.length, controller.signal)
        loaded.push(...page.items)
      }
      if (controller.signal.aborted) return
      setRuns(current => {
        const merged = offset ? [...current, ...loaded] : [...loaded]
        const active = current.find(run => run.id === selection.current)
        if (active && !merged.some(run => run.id === active.id)) merged.push(active)
        return [...new Map(merged.map(run => [run.id, run])).values()]
      })
      setTotal(page.total)
      setNextOffset(offset + loaded.length)
      const first = loaded.find(run => run.playable && run.label !== REFERENCE_LABEL) ?? loaded.find(run => run.playable)
      if (!selection.current && first) {
        selection.current = first.id; setSelected(first.id)
        setScenario(first.scenario_ids.includes(1) ? 1 : first.scenario_ids[0])
      }
      setLoading(false)
    }
    void load().catch(reason => {
      if (!controller.signal.aborted) { setError(reason instanceof Error ? reason.message : String(reason)); setLoading(false) }
    })
    return () => controller.abort()
  }, [source, refresh, offset])

  return <main className="sim-app" style={designVars as CSSProperties}>
    <header className="sim-frame-heading"><p className="sim-frame-eyebrow">PROVIDER · SIMENV / GEOGRAPHY</p>
      <h1>World supply network</h1><p className="sim-frame-subtitle">Recorded supply-chain playback</p></header>
    <div className="sim-playback-sidebar">
      <RunSelector runs={runs} selected={selected} scenario={scenario} loading={loading} error={error}
      hasMore={nextOffset < total} onRefresh={refreshRuns} onMore={() => setOffset(nextOffset)}
      onRun={id => {
        const run = runs.find(item => item.id === id)
        if (!run?.playable) return
        opening.current?.abort()
        selection.current = id; setSelected(id)
        setScenario(run.scenario_ids.includes(1) ? 1 : run.scenario_ids[0])
      }} onScenario={id => { opening.current?.abort(); setScenario(id) }} />
      <div ref={setImpactSlot} />
    </div>
    {selected ? <SelectedPlayback key={`${selected}:${scenario}`} source={source} run={selected} scenario={scenario} runs={runs} impactSlot={impactSlot} />
      : <div className="sim-playback-message">Select a completed run for playback.</div>}
    <ScenarioConfigurator meta={{ pdl: 's1-soja.pdl.yaml', scenario: '', ticks: 0, generatedAt: '', honestyNote: '' }} onCompleted={refreshRuns} onViewResults={viewResults} />
  </main>
}

function SelectedPlayback({ source, run, scenario, runs, impactSlot }: { source: PlaybackSource; run: string; scenario: number; runs: RunSummary[]; impactSlot: HTMLElement | null }) {
  const [referenceChoice, setReferenceChoice] = useState(source.mode === 'static' ? 'start' : 'auto')
  const automatic = referenceChoice === 'auto'
  const preparation = useAutomaticReference(source, run, scenario, automatic)
  const playback = usePlayback(source, run, scenario, automatic ? preparation.reference ?? null : referenceChoice)
  const reference = playback.reference
  const comparisonReady = !automatic || (preparation.phase === 'ready' && !!(reference.frame || reference.error))
  const [selectedNode, setSelectedNode] = useState('')
  const [impactExpanded, setImpactExpanded] = useState(true)
  const impactControlsId = useId()
  const selectedComponent = selectedNode || playback.scene?.nodes[0]?.id || ''
  const displayScene = useMemo(() => playback.scene ? presentScene(playback.scene) : null, [playback.scene])
  const scene = useMemo(() => displayScene ? resolveScene(displayScene.nodes, displayScene.edges) : null, [displayScene])
  const projected = useMemo(() => comparisonReady && playback.scene && playback.frame
    ? projectFrame(playback.scene, playback.frame, reference.frame, playback.baseline) : null, [comparisonReady, playback.scene, playback.frame, playback.baseline, reference.frame])
  const selectFromMap = useCallback((id: string) => {
    setSelectedNode(id); setImpactExpanded(true)
  }, [])
  useEffect(() => {
    for (const item of scene?.unplaced ?? []) console.warn(`[gazetteer] not rendered — ${item.kind} "${item.id}": ${item.reason}`)
  }, [scene])
  useEffect(() => {
    const began = performance.now()
    const id = requestAnimationFrame(() => measure('playback.commit-to-paint', began))
    return () => cancelAnimationFrame(id)
  }, [playback.frame])
  return <>
    {scene && <Profiler id="globe" onRender={(_id, _phase, duration) => {
      measure('playback.react', performance.now() - duration)
    }}><GlobeView markers={scene.markers} edges={scene.edges} markerIntensity={projected?.markerIntensity} edgeIntensity={projected?.edgeIntensity}
      selectedNode={selectedComponent} onSelectNode={selectFromMap} /></Profiler>}
    {impactSlot && createPortal(<aside className="sim-status-panel" aria-label="Disturbance impact">
      <header className="sim-status-panel-header"><h2>Disturbance impact</h2>
        <button type="button" aria-expanded={impactExpanded} aria-controls={impactControlsId}
          aria-label={`${impactExpanded ? 'Hide' : 'Show'} disturbance impact`}
          onClick={() => setImpactExpanded(value => !value)}>{impactExpanded ? 'Hide' : 'Show'}</button>
      </header>
      <div id={impactControlsId} hidden={!impactExpanded}>
        <ReferenceSelector runs={runs} choice={referenceChoice} onChange={setReferenceChoice}
        automaticAvailable={source.mode === 'recorded'}
        explanation={reference.explanation}
        loading={automatic && preparation.phase !== 'ready' ? preparation.phase !== 'error' : reference.loading}
        error={automatic && preparation.phase === 'error' ? preparation.message : reference.error}
        preparation={automatic && preparation.phase !== 'ready' && preparation.phase !== 'error' ? preparation.message : undefined}
        onRetry={automatic && preparation.phase === 'error' ? preparation.retry : reference.retry} />
      <StatusLegend />
      <StableInspector>
      {displayScene && playback.frame && projected && <StatusPanel scene={displayScene} projected={projected}
        period={playback.frame.period} selected={selectedComponent} onSelect={setSelectedNode}
        reference={[reference.explanation, reference.error].filter(Boolean).join(' ')} />}
      </StableInspector>
      </div>
    </aside>, impactSlot)}
    <div className="sim-playback-notice">
      {playback.buffering && (!automatic || preparation.phase === 'ready') && <p className="sim-playback-message" role="status">Buffering playback…</p>}
      {playback.error && <div className="sim-playback-message"><p role="alert">{playback.error}</p>
        <button type="button" onClick={playback.retryPlayback}>Retry playback</button></div>}
    </div>
    {playback.frame && playback.scene && <Timeline period={playback.frame.period} minPeriod={playback.scene.min_period}
      maxPeriod={playback.scene.max_period} playing={playback.playing} env={projected?.env ?? null}
      indicators={projected?.indicators}
      onSeek={playback.seek} onTogglePlay={playback.toggle} />}
    <footer className="sim-frame-meta"><span>Displayed recorded results: {source.name} · {run} · scenario {scenario}</span>
      <p className="sim-frame-honesty">{playback.scene?.honesty_note}</p></footer>
  </>
}
