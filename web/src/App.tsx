import { Profiler, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import type { PlaybackSource, RunSummary } from './data/playback'
import { resolveScene } from './data/gazetteer'
import { designVars } from './design/tokens'
import GlobeView from './globe/GlobeView'
import ScenarioConfigurator from './configurator/ScenarioConfigurator'
import Timeline from './playback/Timeline'
import RunSelector from './playback/RunSelector'
import { usePlayback } from './playback/usePlayback'
import { projectFrame } from './playback/frame'
import { measure } from './playback/measure'
import './app.css'

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
  const selection = useRef('')
  const refreshRuns = useCallback(() => { setOffset(0); setRefresh(value => value + 1) }, [])

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
      const first = loaded.find(run => run.playable)
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
    <RunSelector runs={runs} selected={selected} scenario={scenario} loading={loading} error={error}
      hasMore={nextOffset < total} onRefresh={refreshRuns} onMore={() => setOffset(nextOffset)}
      onRun={id => {
        const run = runs.find(item => item.id === id)
        if (!run?.playable) return
        selection.current = id; setSelected(id)
        setScenario(run.scenario_ids.includes(1) ? 1 : run.scenario_ids[0])
      }} onScenario={setScenario} />
    {selected ? <SelectedPlayback key={`${selected}:${scenario}`} source={source} run={selected} scenario={scenario} />
      : <div className="sim-playback-message">Select a completed run for playback.</div>}
    <ScenarioConfigurator meta={{ pdl: 's1-soja.pdl.yaml', scenario: '', ticks: 0, generatedAt: '', honestyNote: '' }} onCompleted={refreshRuns} />
  </main>
}

function SelectedPlayback({ source, run, scenario }: { source: PlaybackSource; run: string; scenario: number }) {
  const playback = usePlayback(source, run, scenario)
  const scene = useMemo(() => playback.scene ? resolveScene(playback.scene.nodes, playback.scene.edges) : null, [playback.scene])
  const projected = useMemo(() => playback.scene && playback.frame && playback.baseline
    ? projectFrame(playback.scene, playback.frame, playback.baseline) : null, [playback.scene, playback.frame, playback.baseline])
  useEffect(() => {
    for (const item of scene?.unplaced ?? []) console.warn(`[gazetteer] not rendered — ${item.kind} "${item.id}": ${item.reason}`)
  }, [scene])
  useEffect(() => {
    const began = performance.now()
    const id = requestAnimationFrame(() => measure('playback.commit-to-paint', began))
    return () => cancelAnimationFrame(id)
  }, [playback.frame])
  return <>
    {scene && projected && <Profiler id="globe" onRender={(_id, _phase, duration) => {
      measure('playback.react', performance.now() - duration)
    }}><GlobeView markers={scene.markers} edges={scene.edges} markerIntensity={projected.markerIntensity} edgeIntensity={projected.edgeIntensity} /></Profiler>}
    {playback.buffering && <p className="sim-playback-message" role="status">Buffering playback…</p>}
    {playback.error && <div className="sim-playback-message"><p role="alert">{playback.error}</p>
      <button type="button" onClick={playback.retryPlayback}>Retry playback</button></div>}
    {playback.frame && playback.scene && <Timeline period={playback.frame.period} minPeriod={playback.scene.min_period}
      maxPeriod={playback.scene.max_period} playing={playback.playing} env={projected?.env ?? null}
      onSeek={playback.seek} onTogglePlay={playback.toggle} />}
    <footer className="sim-frame-meta"><span>{source.name} · {run} · scenario {scenario}</span>
      <p className="sim-frame-honesty">{playback.scene?.honesty_note}</p></footer>
  </>
}
