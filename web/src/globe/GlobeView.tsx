import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Globe, { type GlobeMethods } from 'react-globe.gl'
import type { Marker, ResolvedEdge, RoutePortMarker } from '../data/gazetteer'
import { arc as arcTok, color, globe as globeTok, marker as markerTok, texture } from '../design/tokens'
import { densifyPolyline, type LatLng } from './geo'
import './labels.css'

type AnchorKind = 'node'
type ArcLayer = 'halo' | 'glow' | 'core'

/** One native `htmlElementsData` entry — a node annotation. */
interface Anchor {
  id: string
  lat: number
  lng: number
  alt: number
  text: string
  anchorKind: AnchorKind
  illustrative: boolean
}

/** One rendered arc. Each edge expands into a halo/glow/core stack for the glow. */
interface ArcDatum {
  layer: ArcLayer
  edgeId: string
  flowKind: ResolvedEdge['kind']
  overland: boolean
  startLat: number
  startLng: number
  endLat: number
  endLng: number
  altitude: number | null
  intensity: number
}

/** One rendered path. Each physical ocean edge gets the same three-layer stack. */
interface PathDatum {
  layer: ArcLayer
  edgeId: string
  flowKind: ResolvedEdge['kind']
  points: LatLng[]
  intensity: number
}

/** A marker with its current (quantised) playback intensity baked in. */
interface PointDatum extends Marker {
  intensity: number
  selected: boolean
}

/**
 * Disruption is a near-step function, so intensity is quantised and the arc/point
 * data is memoised on a signature of those quantised values. The data reference
 * then only changes when disruption actually changes (a handful of times across a
 * whole run) — three-globe reuses arc materials in between, so the dash animation
 * runs uninterrupted instead of restarting every step.
 */
const INTENSITY_STEP = 0.1

function quantise(value: number): number {
  return Math.round(Math.min(1, Math.max(0, value)) / INTENSITY_STEP) * INTENSITY_STEP
}

interface GlobeViewProps {
  markers: Marker[]
  routePortMarkers?: RoutePortMarker[]
  edges: ResolvedEdge[]
  visibleCommercialEdgeIds?: ReadonlySet<string>
  /** Per-node 0..1 disruption intensity for the current playback period. */
  markerIntensity?: Record<string, number>
  /** Per-edge 0..1 disruption intensity for the current playback period. */
  edgeIntensity?: Record<string, number>
}

type Rgb = readonly [number, number, number]

const NO_INTENSITY: Record<string, number> = {}
const NO_VISIBLE_COMMERCIAL_EDGES: ReadonlySet<string> = new Set()

function mix(a: Rgb | readonly number[], b: Rgb, t: number): [number, number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
}

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

function baseMarkerColor(marker: PointDatum): string {
  if (marker.selected) return color.text
  if (marker.role === 'producer') return color.positive
  if (!marker.hasRecordedData) return color.muted
  if (marker.illustrative) return color.warning
  return color.text
}

/** Marker colour tinted toward the disruption red by the current intensity. */
function colorForPoint(marker: PointDatum): string {
  const base = baseMarkerColor(marker)
  if (marker.intensity <= 0.001) return base
  return rgba(mix(hexToRgb(base), arcTok.hot, Math.min(1, marker.intensity) * 0.9), 1)
}

const ARC_LAYERS: ArcLayer[] = ['halo', 'glow', 'core']

function arcSpec(layer: ArcLayer) {
  return layer === 'halo' ? arcTok.halo : layer === 'glow' ? arcTok.glow : arcTok.core
}

/** Arc layer colour, lerped teal → red by the edge intensity. */
function colorForCorridor(datum: ArcDatum | PathDatum, layerAlphaScale = 1): string[] {
  const spec = arcSpec(datum.layer)
  const t = Math.min(1, datum.intensity) * 0.85
  const alphaScale = datum.flowKind === 'commercial' ? arcTok.commercialAlphaScale : 1
  return spec.teal.map((teal) =>
    rgba(mix(teal, arcTok.hot, t), spec.alpha * alphaScale * layerAlphaScale),
  )
}

/**
 * 3D substrate and renderer for an already-resolved scene.
 *
 * Node annotations use globe.gl's NATIVE `htmlElementsData` layer, which
 * projects and occludes them each frame (anchors behind the globe hide
 * automatically) — no manual projection, occlusion, or collision code. The
 * blue-marble texture is pre-lit and carries the look on its own, so there is
 * no custom material, lighting, or post-processing.
 */
export default function GlobeView({
  markers,
  routePortMarkers = [],
  edges,
  visibleCommercialEdgeIds = NO_VISIBLE_COMMERCIAL_EDGES,
  markerIntensity = NO_INTENSITY,
  edgeIntensity = NO_INTENSITY,
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
        anchorKind: 'node',
        illustrative: marker.illustrative,
      })
    }
    return output
  }, [markers])

  // Signatures of the quantised intensities. useMemo compares deps by value, so a
  // new-but-identical signature string keeps the previous data reference — the
  // globe only rebuilds when disruption actually changes.
  const pathEdges = useMemo(
    () =>
      edges.filter(
        (edge) =>
          edge.kind === 'physical' &&
          edge.laneNodeId !== undefined &&
          edge.path !== undefined &&
          edge.path.length > 1,
      ),
    [edges],
  )

  // A lane edge without authored geometry deliberately remains in this set and
  // falls back to an arc. Commercial relationships join only when requested.
  const arcEdges = useMemo(
    () =>
      edges.filter(
        (edge) =>
          (edge.kind === 'commercial' && visibleCommercialEdgeIds.has(edge.id)) ||
          (edge.kind === 'physical' &&
            !(
              edge.laneNodeId !== undefined &&
              edge.path !== undefined &&
              edge.path.length > 1
            )),
      ),
    [edges, visibleCommercialEdgeIds],
  )

  const pathGeometry = useMemo(
    () =>
      pathEdges.map((edge) => ({
        edge,
        points: densifyPolyline(edge.path ?? []),
      })),
    [pathEdges],
  )

  const selectedMarker = useMemo(
    () => markers.find((marker) => marker.role === 'producer') ?? markers[0],
    [markers],
  )
  const markerSig = markers.map((m) => quantise(markerIntensity[m.nodeId] ?? 0)).join(',')
  const arcSig = arcEdges.map((e) => `${e.id}:${quantise(edgeIntensity[e.id] ?? 0)}`).join(',')
  const pathSig = pathEdges.map((e) => `${e.id}:${quantise(edgeIntensity[e.id] ?? 0)}`).join(',')

  const pointData = useMemo<PointDatum[]>(
    () =>
      markers.map((marker) => ({
        ...marker,
        intensity: quantise(markerIntensity[marker.nodeId] ?? 0),
        selected: marker.id === selectedMarker?.id,
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [markers, selectedMarker, markerSig],
  )

  // Each edge becomes three stacked arcs (soft halo, mid glow, bright core).
  const arcData = useMemo<ArcDatum[]>(
    () =>
      arcEdges.flatMap((edge) =>
        ARC_LAYERS.map((layer) => {
          const overland = edge.kind === 'physical' && edge.laneNodeId === undefined
          return {
            layer,
            edgeId: edge.id,
            flowKind: edge.kind,
            overland,
            startLat: edge.startLat,
            startLng: edge.startLng,
            endLat: edge.endLat,
            endLng: edge.endLng,
            altitude: overland ? arcTok.overlandAltitude : null,
            intensity: quantise(edgeIntensity[edge.id] ?? 0),
          }
        }),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [arcEdges, arcSig],
  )

  const pathData = useMemo<PathDatum[]>(
    () =>
      pathGeometry.flatMap(({ edge, points }) =>
        ARC_LAYERS.map((layer) => ({
          layer,
          edgeId: edge.id,
          flowKind: edge.kind,
          points,
          intensity: quantise(edgeIntensity[edge.id] ?? 0),
        })),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pathGeometry, pathSig],
  )

  // The native html layer positions and centres the OUTER node on the projected
  // point each frame; the inner label floats above its marker.
  const makeAnchorElement = useCallback((datum: object) => {
    const anchor = datum as Anchor
    const outer = document.createElement('div')
    outer.className = `sim-anchor sim-anchor--${anchor.anchorKind}`
    const label = document.createElement('div')
    label.className = `sim-label sim-label--${anchor.anchorKind}${
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
    controls.autoRotate = !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    controls.autoRotateSpeed = globeTok.autoRotateSpeed
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.minDistance = globe.getGlobeRadius() * 1.38
    controls.maxDistance = globe.getGlobeRadius() * 6.2
  }, [])

  const mobile = size.width <= 600
  const globeOffset: [number, number] = [0, mobile ? -10 : -8]

  return (
    <div
      className="sim-globe-stage"
      data-visible-arc-count={arcEdges.length}
      data-visible-path-count={pathEdges.length}
      data-route-port-count={routePortMarkers.length}
      data-arc-signature={arcSig}
      data-path-signature={pathSig}
    >
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
          const base = point.selected ? markerTok.selectedRadius : markerTok.radius
          return base * (1 + Math.min(1, point.intensity) * 0.7)
        }}
        pointResolution={18}
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
        arcAltitude={(datum) => (datum as ArcDatum).altitude}
        arcAltitudeAutoScale={arcTok.altitudeAutoScale}
        arcColor={(datum: object) => colorForCorridor(datum as ArcDatum)}
        arcStroke={(datum: object) => {
          const arc = datum as ArcDatum
          const scale = arc.overland
            ? arcTok.overlandStrokeScale
            : arc.flowKind === 'commercial'
              ? arcTok.commercialStrokeScale
              : 1
          return arcSpec(arc.layer).stroke * scale
        }}
        arcDashLength={(datum: object) => {
          const arc = datum as ArcDatum
          if (arc.flowKind === 'commercial' && arc.layer === 'core') {
            return arcTok.commercialDashLength
          }
          return arc.layer === 'core' ? arcTok.coreDashLength : 1
        }}
        arcDashGap={(datum: object) => {
          const arc = datum as ArcDatum
          if (arc.flowKind === 'commercial' && arc.layer === 'core') {
            return arcTok.commercialDashGap
          }
          return arc.layer === 'core' ? arcTok.coreDashGap : 0
        }}
        arcDashAnimateTime={(datum: object) => {
          const arc = datum as ArcDatum
          if (arc.layer !== 'core') return 0
          return arc.flowKind === 'commercial'
            ? arcTok.commercialDashAnimateMs
            : arcTok.coreDashAnimateMs
        }}
        arcsTransitionDuration={0}
        pathsData={pathData}
        pathPoints={(datum) => (datum as PathDatum).points}
        pathPointLat={(point) => (point as LatLng).lat}
        pathPointLng={(point) => (point as LatLng).lng}
        pathPointAlt={arcTok.pathAltitude}
        pathResolution={2}
        pathColor={(datum: object) => {
          const path = datum as PathDatum
          return colorForCorridor(path, arcTok.pathAlphaScale[path.layer])
        }}
        pathStroke={(datum: object) => {
          const path = datum as PathDatum
          return arcSpec(path.layer).stroke * arcTok.pathStrokeScale[path.layer]
        }}
        pathDashLength={(datum: object) => {
          const layer = (datum as PathDatum).layer
          return layer === 'halo' ? 1 : arcTok.pathCoreDashLength
        }}
        pathDashGap={(datum: object) => {
          const layer = (datum as PathDatum).layer
          return layer === 'halo' ? 0 : arcTok.pathCoreDashGap
        }}
        pathDashInitialGap={(datum: object) =>
          (datum as PathDatum).layer === 'glow' ? arcTok.pathGlowDashInitialGap : 0
        }
        pathDashAnimateTime={(datum: object) =>
          (datum as PathDatum).layer === 'halo' ? 0 : arcTok.pathCoreDashAnimateMs
        }
        pathTransitionDuration={0}
        labelsData={routePortMarkers}
        labelLat={(datum) => (datum as RoutePortMarker).lat}
        labelLng={(datum) => (datum as RoutePortMarker).lng}
        labelText={(datum) => (datum as RoutePortMarker).label}
        labelSize={markerTok.portLabelSize}
        labelDotRadius={markerTok.portDotRadius}
        labelColor={(datum) =>
          (datum as RoutePortMarker).role === 'origin'
            ? markerTok.portOriginColor
            : markerTok.portDestinationColor
        }
        labelAltitude={markerTok.portAltitude}
        labelResolution={2}
        labelsTransitionDuration={0}
        htmlElementsData={anchors}
        htmlLat={(datum: object) => (datum as Anchor).lat}
        htmlLng={(datum: object) => (datum as Anchor).lng}
        htmlAltitude={(datum: object) => (datum as Anchor).alt}
        htmlElement={makeAnchorElement}
      />
    </div>
  )
}
