import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Globe, { type GlobeMethods } from 'react-globe.gl'
import type { Marker, ResolvedEdge } from '../data/gazetteer'
import { arc as arcTok, color, globe as globeTok, marker as markerTok, texture } from '../design/tokens'
import { arcApex } from './geo'
import { statusColor } from '../design/status'
import './labels.css'

type LabelKind = 'node' | 'edge'
type ArcLayer = 'halo' | 'glow' | 'core'

/** One native `htmlElementsData` entry — a node or edge annotation. */
interface Anchor {
  id: string
  lat: number
  lng: number
  alt: number
  text: string
  kind: LabelKind
  illustrative: boolean
}

/** One rendered arc. Each edge expands into a halo/glow/core stack for the glow. */
interface ArcDatum {
  layer: ArcLayer
  edgeId: string
  startLat: number
  startLng: number
  endLat: number
  endLng: number
  intensity: number | null
}

/** A marker with its current (quantised) playback intensity baked in. */
interface PointDatum extends Marker {
  intensity: number | null
}

interface GlobeViewProps {
  markers: Marker[]
  edges: ResolvedEdge[]
  /** Per-node 0..1 disruption intensity for the current playback period. */
  markerIntensity?: Record<string, number | null>
  /** Per-edge 0..1 disruption intensity for the current playback period. */
  edgeIntensity?: Record<string, number | null>
  selectedNode?: string
  onSelectNode?: (id: string) => void
}

const NO_INTENSITY: Record<string, number | null> = {}

function rgba([r, g, b]: [number, number, number], alpha: number): string {
  return `rgba(${Math.round(r)},${Math.round(g)},${Math.round(b)},${alpha})`
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ]
}

/** Selection and geographic annotations never override simulation status fill. */
function colorForPoint(marker: PointDatum): string {
  return statusColor(marker.intensity)
}

const ARC_LAYERS: ArcLayer[] = ['halo', 'glow', 'core']

function arcSpec(layer: ArcLayer) {
  return layer === 'halo' ? arcTok.halo : layer === 'glow' ? arcTok.glow : arcTok.core
}

/** Arc layer colour, lerped teal → red by the edge intensity. */
function colorForArc(datum: ArcDatum): string[] {
  const spec = arcSpec(datum.layer)
  return [rgba(hexToRgb(statusColor(datum.intensity)), spec.alpha)]
}

/**
 * 3D substrate and renderer for an already-resolved scene.
 *
 * Node and edge annotations use globe.gl's NATIVE `htmlElementsData` layer,
 * which projects and occludes them each frame (anchors behind the globe hide
 * automatically) — no manual projection, occlusion, or collision code. The
 * blue-marble texture is pre-lit and carries the look on its own, so there is
 * no custom material, lighting, or post-processing.
 */
export default function GlobeView({
  markers,
  edges,
  markerIntensity = NO_INTENSITY,
  edgeIntensity = NO_INTENSITY,
  selectedNode,
  onSelectNode,
}: GlobeViewProps) {
  const globeRef = useRef<GlobeMethods | undefined>(undefined)
  const [size, setSize] = useState({
    width: window.innerWidth || 1280,
    height: window.innerHeight || 720,
  })

  useEffect(() => {
    const onResize = () =>
      setSize({ width: window.innerWidth || 1280, height: window.innerHeight || 720 })
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const anchors = useMemo<Anchor[]>(() => {
    const output: Anchor[] = []
    for (const marker of markers) {
      output.push({
        id: `node:${marker.id}`,
        lat: marker.lat,
        lng: marker.lng,
        alt: markerTok.altitude,
        text: marker.label,
        kind: 'node',
        illustrative: marker.illustrative,
      })
    }
    for (const edge of edges) {
      // Anchor the edge label to the arc's actual rendered apex (not the
      // great-circle midpoint) so it sits on the curve for arcs of any length.
      const apex = arcApex(
        { lat: edge.startLat, lng: edge.startLng },
        { lat: edge.endLat, lng: edge.endLng },
        arcTok.altitudeAutoScale,
      )
      output.push({
        id: `edge:${edge.id}`,
        lat: apex.lat,
        lng: apex.lng,
        alt: apex.alt,
        text: edge.label,
        kind: 'edge',
        illustrative: false,
      })
    }
    return output
  }, [markers, edges])

  // Exact semantic values preserve threshold boundaries and unknown states.
  const markerSig = markers.map(m => String(markerIntensity[m.nodeId] ?? null)).join(',')
  const edgeSig = edges.map(e => String(edgeIntensity[e.id] ?? null)).join(',')

  const pointData = useMemo<PointDatum[]>(
    () => markers.map((marker) => ({ ...marker, intensity: markerIntensity[marker.nodeId] ?? null })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [markers, markerSig],
  )

  // Each edge becomes three stacked arcs (soft halo, mid glow, bright core).
  const arcData = useMemo<ArcDatum[]>(
    () =>
      edges.flatMap((edge) =>
        ARC_LAYERS.map((layer) => ({
          layer,
          edgeId: edge.id,
          startLat: edge.startLat,
          startLng: edge.startLng,
          endLat: edge.endLat,
          endLng: edge.endLng,
          intensity: edgeIntensity[edge.id] ?? null,
        })),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [edges, edgeSig],
  )

  const selectedMarker = useMemo(
    () => markers.find((marker) => marker.nodeId === selectedNode),
    [markers, selectedNode],
  )

  // The native html layer positions and centres the OUTER node on the projected
  // point each frame; the inner label offsets itself (nodes float above their
  // marker, edge labels sit on the arc apex).
  const makeAnchorElement = useCallback((datum: object) => {
    const anchor = datum as Anchor
    const outer = document.createElement('div')
    outer.className = `sim-anchor sim-anchor--${anchor.kind}`
    const label = document.createElement('div')
    label.className = `sim-label sim-label--${anchor.kind}${
      anchor.illustrative ? ' sim-label--illustrative' : ''
    }`
    label.textContent = anchor.text
    outer.appendChild(label)
    return outer
  }, [])

  const handleGlobeReady = useCallback(() => {
    const globe = globeRef.current
    if (!globe) return
    const mobile = window.innerWidth <= 600
    globe.pointOfView(
      { lat: 7, lng: -54, altitude: mobile ? globeTok.cameraMobile : globeTok.cameraDesktop },
      0,
    )

    const controls = globe.controls()
    controls.autoRotate = true
    controls.autoRotateSpeed = globeTok.autoRotateSpeed
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.minDistance = globe.getGlobeRadius() * 1.38
    controls.maxDistance = globe.getGlobeRadius() * 6.2
  }, [])

  const mobile = size.width <= 600
  const globeOffset: [number, number] = [0, mobile ? -10 : -8]

  return (
    <div className="sim-globe-stage">
      <Globe
        ref={globeRef}
        onGlobeReady={handleGlobeReady}
        width={size.width}
        height={size.height}
        globeOffset={globeOffset}
        rendererConfig={{ antialias: true, alpha: false }}
        backgroundColor={globeTok.background}
        backgroundImageUrl={texture.nightSky}
        globeImageUrl={texture.earth}
        bumpImageUrl={texture.bump}
        showAtmosphere
        atmosphereColor={globeTok.atmosphere}
        atmosphereAltitude={globeTok.atmosphereAltitude}
        pointsData={pointData}
        pointLat={(datum) => (datum as PointDatum).lat}
        pointLng={(datum) => (datum as PointDatum).lng}
        pointColor={(datum: object) => colorForPoint(datum as PointDatum)}
        pointAltitude={markerTok.altitude}
        pointRadius={(datum: object) => {
          const point = datum as PointDatum
           return point.nodeId === selectedNode ? markerTok.selectedRadius : markerTok.radius
        }}
        pointResolution={18}
        onPointClick={datum => onSelectNode?.((datum as PointDatum).nodeId)}
        pointsMerge={false}
        pointsTransitionDuration={0}
        ringsData={selectedMarker ? [selectedMarker] : []}
        ringLat={(datum) => (datum as Marker).lat}
        ringLng={(datum) => (datum as Marker).lng}
        ringAltitude={markerTok.altitude * 0.5}
        ringColor={[color.text, 'rgba(185, 233, 255, 0.42)', 'rgba(67, 183, 255, 0)']}
        ringMaxRadius={markerTok.haloRadius}
        ringPropagationSpeed={markerTok.haloSpeed}
        ringRepeatPeriod={markerTok.haloRepeatMs}
        ringResolution={96}
        arcsData={arcData}
        arcStartLat={(datum) => (datum as ArcDatum).startLat}
        arcStartLng={(datum) => (datum as ArcDatum).startLng}
        arcEndLat={(datum) => (datum as ArcDatum).endLat}
        arcEndLng={(datum) => (datum as ArcDatum).endLng}
        arcAltitudeAutoScale={arcTok.altitudeAutoScale}
        arcColor={(datum: object) => colorForArc(datum as ArcDatum)}
        arcStroke={(datum: object) => arcSpec((datum as ArcDatum).layer).stroke}
        arcDashLength={(datum: object) =>
          (datum as ArcDatum).layer === 'core' ? arcTok.coreDashLength : 1
        }
        arcDashGap={(datum: object) => ((datum as ArcDatum).layer === 'core' ? arcTok.coreDashGap : 0)}
        arcDashAnimateTime={(datum: object) =>
          (datum as ArcDatum).layer === 'core' ? arcTok.coreDashAnimateMs : 0
        }
        arcsTransitionDuration={0}
        htmlElementsData={anchors}
        htmlLat={(datum: object) => (datum as Anchor).lat}
        htmlLng={(datum: object) => (datum as Anchor).lng}
        htmlAltitude={(datum: object) => (datum as Anchor).alt}
        htmlElement={makeAnchorElement}
      />
    </div>
  )
}
