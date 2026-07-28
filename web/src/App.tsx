import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import type { DataSource } from './data/source'
import type { Bundle } from './data/types'
import { resolveScene } from './data/gazetteer'
import { designVars } from './design/tokens'
import GlobeView from './globe/GlobeView'
import './app.css'

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

  if (!bundle || !scene) {
    return (
      <main className="sim-app sim-app--message" style={themeStyle} aria-live="polite">
        <p>Resolving simulation geography…</p>
      </main>
    )
  }

  return (
    <main className="sim-app" style={themeStyle}>
      <GlobeView markers={scene.markers} edges={scene.edges} />

      <header className="sim-frame-heading">
        <p className="sim-frame-eyebrow">PROVIDER · SIMENV / GEOGRAPHY</p>
        <h1>World supply network</h1>
        <p className="sim-frame-subtitle">Soy flows across the Atlantic system</p>
      </header>

      <footer className="sim-frame-meta">
        <div className="sim-frame-stats" aria-label="Scene summary">
          <span className="sim-frame-signal" aria-hidden="true" />
          <span>{scene.markers.length} markers</span>
          <span className="sim-frame-divider" aria-hidden="true" />
          <span>{scene.edges.length} corridors</span>
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
