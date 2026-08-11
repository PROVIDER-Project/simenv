import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import type { DataSource } from './data/source'
import type { Bundle } from './data/types'
import { resolveScene } from './data/gazetteer'
import { designVars } from './design/tokens'
import GlobeView from './globe/GlobeView'
import { buildDynamics } from './playback/dynamics'
import Timeline from './playback/Timeline'
import './app.css'

/** How long each playback step is held, in milliseconds. */
const STEP_INTERVAL_MS = 60

interface AppProps {
  /** Injected at the composition root. The view never names a concrete source. */
  source: DataSource
}

function App({ source }: AppProps) {
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    source
      .getBundle()
      .then((nextBundle) => {
        if (!cancelled) setBundle(nextBundle)
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason))
      })
    return () => {
      cancelled = true
    }
  }, [source])

  return <MapView bundle={bundle} sourceName={source.name} error={error} />
}

interface MapViewProps {
  bundle: Bundle | null
  sourceName: string
  error: string | null
}

const themeStyle = designVars as CSSProperties

function MapView({ bundle, sourceName, error }: MapViewProps) {
  // Unknown placements are deliberately absent, never silently replaced by a
  // country centroid. The console warning is the visible integration signal.
  const scene = useMemo(
    () => (bundle ? resolveScene(bundle.nodes, bundle.edges) : null),
    [bundle],
  )

  const dynamics = useMemo(() => (bundle ? buildDynamics(bundle) : null), [bundle])
  const stepCount = dynamics?.periods.length ?? 0

  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [visibleCommercialGroupIds, setVisibleCommercialGroupIds] = useState<Set<string>>(
    () => new Set(),
  )

  const visibleCommercialEdgeIds = useMemo(
    () =>
      new Set(
        (scene?.commercialGroups ?? [])
          .filter((group) => visibleCommercialGroupIds.has(group.id))
          .flatMap((group) => group.edgeIds),
      ),
    [scene, visibleCommercialGroupIds],
  )

  // Reset and auto-play whenever a new bundle (with more than one step) loads.
  useEffect(() => {
    setIndex(0)
    setPlaying(stepCount > 1)
  }, [stepCount])

  useEffect(() => {
    if (!playing || stepCount <= 1) return
    const id = window.setInterval(() => setIndex((i) => (i + 1) % stepCount), STEP_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [playing, stepCount])

  useEffect(() => {
    if (!scene) return
    for (const unplaced of scene.unplaced) {
      console.warn(
        `[gazetteer] not rendered — ${unplaced.kind} "${unplaced.id}": ${unplaced.reason}`,
      )
    }
  }, [scene])

  if (error) {
    return (
      <main className="sim-app sim-app--message" style={themeStyle}>
        <p role="alert">Failed to load the simulation bundle: {error}</p>
      </main>
    )
  }

  if (!bundle || !scene || !dynamics) {
    return (
      <main className="sim-app sim-app--message" style={themeStyle} aria-live="polite">
        <p>Resolving simulation geography…</p>
      </main>
    )
  }

  const firstPeriod = dynamics.periods[0] ?? 0
  const lastPeriod = dynamics.periods[stepCount - 1] ?? 0
  const period = dynamics.periods[index] ?? firstPeriod
  const frame = dynamics.frameAt(period)
  const env = dynamics.envAt(period)
  const visibleCorridorCount = scene.edges.filter(
    (edge) => edge.kind === 'physical' || visibleCommercialEdgeIds.has(edge.id),
  ).length

  return (
    <main className="sim-app" style={themeStyle}>
      <GlobeView
        markers={scene.markers}
        routePortMarkers={scene.routePortMarkers}
        edges={scene.edges}
        visibleCommercialEdgeIds={visibleCommercialEdgeIds}
        markerIntensity={frame.markerIntensity}
        edgeIntensity={frame.edgeIntensity}
      />

      <header className="sim-frame-heading">
        <p className="sim-frame-eyebrow">PROVIDER · SIMENV / GEOGRAPHY</p>
        <h1>World supply network</h1>
        <p className="sim-frame-subtitle">Soy flows across the Atlantic system</p>
      </header>

      <div className="sim-contract-groups">
        <span className="sim-contract-groups__label" id="commercial-groups-label">
          Commercial structure <small>inferred, not measured</small>
        </span>
        <div className="sim-contract-groups__controls" role="group" aria-labelledby="commercial-groups-label">
          {scene.commercialGroups.map((group) => {
            const visible = visibleCommercialGroupIds.has(group.id)
            return (
              <button
                className="sim-contract-toggle"
                type="button"
                key={group.id}
                aria-pressed={visible}
                data-commercial-group-id={group.id}
                data-commercial-edge-count={group.edgeIds.length}
                title={`${group.label}: structural geographic grouping, not a measured flow`}
                onClick={() =>
                  setVisibleCommercialGroupIds((current) => {
                    const next = new Set(current)
                    if (next.has(group.id)) next.delete(group.id)
                    else next.add(group.id)
                    return next
                  })
                }
              >
                <span className="sim-contract-toggle__signal" aria-hidden="true" />
                {group.label}
              </button>
            )
          })}
        </div>
      </div>

      {stepCount > 1 && (
        <Timeline
          period={period}
          minPeriod={firstPeriod}
          maxPeriod={lastPeriod}
          playing={playing}
          env={env}
          onSeek={(next) => {
            setPlaying(false)
            setIndex(Math.max(0, Math.min(stepCount - 1, next - firstPeriod)))
          }}
          onTogglePlay={() => setPlaying((value) => !value)}
        />
      )}

      <footer className="sim-frame-meta">
        <div className="sim-frame-stats" aria-label="Scene summary">
          <span className="sim-frame-signal" aria-hidden="true" />
          <span>{scene.markers.length + scene.routePortMarkers.length} markers</span>
          <span className="sim-frame-divider" aria-hidden="true" />
          <span>{visibleCorridorCount} corridors</span>
          <span className="sim-frame-divider" aria-hidden="true" />
          <span>
            source <code>{sourceName}</code>
          </span>
          {scene.unplaced.length > 0 && (
            <span className="sim-frame-unplaced">{scene.unplaced.length} unplaced</span>
          )}
        </div>
        <p className="sim-frame-honesty">{bundle.meta.honestyNote}</p>
      </footer>
    </main>
  )
}

export default App
