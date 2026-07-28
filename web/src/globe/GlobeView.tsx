import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Globe, { type GlobeMethods } from 'react-globe.gl'
import * as THREE from 'three'
import type { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import type { Marker, ResolvedEdge } from '../data/gazetteer'
import { arc as arcTok, color, globe as globeTok, marker as markerTok } from '../design/tokens'
import {
  buildBasemapTextures,
  buildSpaceCanvas,
  parseFeatureCollection,
  type GeoFeature,
} from './basemap'
import { greatCircleMidpoint } from './geo'
import './labels.css'

const COLLIDE_PAD = 3
const BASEMAP_URL = '/geo/world_countries.geojson'
const SELECTED_MARKER_ID = 'bra_farmers'

type LabelKind = 'node' | 'edge'

interface LabelDatum {
  id: string
  lat: number
  lng: number
  alt: number
  text: string
  kind: LabelKind
  illustrative: boolean
  priority: number
  anchorEl: HTMLDivElement | null
  labelEl: HTMLDivElement | null
}

interface SurfaceState {
  status: 'loading' | 'ready' | 'error'
  imageUrl: string | null
  bumpUrl: string | null
  features: GeoFeature[]
}

interface GlobeViewProps {
  markers: Marker[]
  edges: ResolvedEdge[]
}

function colorForMarker(marker: Marker): string {
  if (marker.id === SELECTED_MARKER_ID) return color.text
  if (marker.role === 'producer') return color.positive
  if (!marker.hasRecordedData) return color.muted
  if (marker.illustrative) return color.warning
  return color.text
}

/**
 * 3D substrate and renderer for an already-resolved scene.
 *
 * Textured/elevated land and react-globe.gl's CSS2D html layer conflict in the
 * installed renderer stack. Annotations therefore live in a controlled DOM
 * overlay and use the library's own `getScreenCoords` projection each frame.
 * This preserves all annotation contracts while freeing surface/bump/polygon
 * and ring layers for the reference design.
 */
export default function GlobeView({ markers, edges }: GlobeViewProps) {
  const globeRef = useRef<GlobeMethods | undefined>(undefined)
  const bloomRef = useRef<UnrealBloomPass | null>(null)
  const composerRef = useRef<EffectComposer | null>(null)
  const [size, setSize] = useState({ width: window.innerWidth, height: window.innerHeight })
  const [surface, setSurface] = useState<SurfaceState>({
    status: 'loading',
    imageUrl: null,
    bumpUrl: null,
    features: [],
  })

  useEffect(() => {
    const onResize = () => setSize({ width: window.innerWidth, height: window.innerHeight })
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    async function loadSurface() {
      try {
        const response = await fetch(BASEMAP_URL, { signal: controller.signal })
        if (!response.ok) throw new Error(`Basemap request failed with HTTP ${response.status}`)
        const input: unknown = await response.json()
        const features = parseFeatureCollection(input)
        const textures = buildBasemapTextures(features, {
          ocean: globeTok.ocean,
          land: globeTok.land,
          coast: globeTok.coast,
          cityLight: globeTok.cityLight,
          cityWarm: globeTok.cityWarm,
        })
        if (!textures) throw new Error('Browser could not create the basemap canvases')
        if (controller.signal.aborted) return
        setSurface({
          status: 'ready',
          imageUrl: textures.color.toDataURL('image/png'),
          bumpUrl: textures.bump.toDataURL('image/png'),
          features,
        })
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === 'AbortError') return
        console.error('[globe] offline basemap unavailable', error)
        setSurface({ status: 'error', imageUrl: null, bumpUrl: null, features: [] })
      }
    }

    void loadSurface()
    return () => controller.abort()
  }, [])

  const labels = useMemo<LabelDatum[]>(() => {
    const output: LabelDatum[] = []
    markers.forEach((marker, index) => {
      output.push({
        id: `node:${marker.id}`,
        lat: marker.lat,
        lng: marker.lng,
        alt: markerTok.altitude,
        text: marker.label,
        kind: 'node',
        illustrative: marker.illustrative,
        priority: index,
        anchorEl: null,
        labelEl: null,
      })
    })
    edges.forEach((edge, index) => {
      const midpoint = greatCircleMidpoint(
        { lat: edge.startLat, lng: edge.startLng },
        { lat: edge.endLat, lng: edge.endLng },
      )
      output.push({
        id: `edge:${edge.id}`,
        lat: midpoint.lat,
        lng: midpoint.lng,
        alt: arcTok.altitude,
        text: edge.label,
        kind: 'edge',
        illustrative: false,
        priority: 1000 + index,
        anchorEl: null,
        labelEl: null,
      })
    })
    return output
  }, [markers, edges])

  const selectedMarker = useMemo(
    () => markers.find((marker) => marker.id === SELECTED_MARKER_ID) ?? markers[0],
    [markers],
  )

  const spaceImageUrl = useMemo(() => buildSpaceCanvas()?.toDataURL('image/png') ?? null, [])
  const globeMaterial = useMemo(
    () =>
      new THREE.MeshPhongMaterial({
        color: 0xffffff,
        emissive: new THREE.Color(globeTok.ocean),
        emissiveIntensity: 0.3,
        bumpScale: 0.66,
        shininess: 6,
        specular: new THREE.Color('#38596F'),
      }),
    [],
  )

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

    const ambient = new THREE.AmbientLight(0x6c99b5, 0.82)
    const key = new THREE.DirectionalLight(0xc7efff, 1.38)
    key.position.set(-220, 90, 260)
    const rim = new THREE.DirectionalLight(0x43b7ff, 0.92)
    rim.position.set(220, -60, -180)
    globe.lights([ambient, key, rim])

    const renderer = globe.renderer()
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 0.96
    renderer.outputColorSpace = THREE.SRGBColorSpace

    if (!bloomRef.current) {
      const bloom = new UnrealBloomPass(
        new THREE.Vector2(window.innerWidth, window.innerHeight),
        0.38,
        0.42,
        0.82,
      )
      bloomRef.current = bloom
      composerRef.current = globe.postProcessingComposer()
      composerRef.current.addPass(bloom)
    }
  }, [])

  useEffect(
    () => () => {
      if (composerRef.current && bloomRef.current) composerRef.current.removePass(bloomRef.current)
      bloomRef.current?.dispose()
      bloomRef.current = null
      composerRef.current = null
      globeMaterial.dispose()
    },
    [globeMaterial],
  )

  // Project, occlude and greedily de-conflict the overlay every rendered frame.
  useEffect(() => {
    let frame = 0
    const projectLabels = () => {
      const globe = globeRef.current
      if (globe) {
        const candidates: LabelDatum[] = []
        for (const label of labels) {
          if (!label.anchorEl || !label.labelEl || isOccluded(globe, label)) {
            if (label.anchorEl) label.anchorEl.style.display = 'none'
            label.labelEl?.classList.remove('sim-label--collide')
            continue
          }
          const screen = globe.getScreenCoords(label.lat, label.lng, label.alt)
          if (!Number.isFinite(screen.x) || !Number.isFinite(screen.y)) {
            label.anchorEl.style.display = 'none'
            continue
          }
          label.anchorEl.style.display = 'block'
          label.anchorEl.style.transform = `translate3d(${screen.x}px, ${screen.y}px, 0)`
          label.labelEl.classList.remove('sim-label--collide')
          candidates.push(label)
        }

        const placed: Array<{ x1: number; y1: number; x2: number; y2: number }> = []
        candidates.sort((a, b) => a.priority - b.priority)
        for (const label of candidates) {
          const rect = label.labelEl!.getBoundingClientRect()
          const isOutsideViewport =
            rect.left < 4 ||
            rect.right > size.width - 4 ||
            rect.top < 4 ||
            rect.bottom > size.height - 4
          if (isOutsideViewport) {
            label.labelEl!.classList.add('sim-label--collide')
            continue
          }
          const box = {
            x1: rect.left - COLLIDE_PAD,
            y1: rect.top - COLLIDE_PAD,
            x2: rect.right + COLLIDE_PAD,
            y2: rect.bottom + COLLIDE_PAD,
          }
          const overlaps = placed.some(
            (other) =>
              !(box.x2 < other.x1 || box.x1 > other.x2 || box.y2 < other.y1 || box.y1 > other.y2),
          )
          if (overlaps) label.labelEl!.classList.add('sim-label--collide')
          else placed.push(box)
        }
      }
      frame = requestAnimationFrame(projectLabels)
    }
    frame = requestAnimationFrame(projectLabels)
    return () => cancelAnimationFrame(frame)
  }, [labels, size])

  const mobile = size.width <= 600
  const globeOffset: [number, number] = [0, mobile ? -10 : -8]

  return (
    <div
      className="sim-globe-stage"
      data-surface-status={surface.status}
      data-land-features={surface.features.length}
    >
      <Globe
        ref={globeRef}
        onGlobeReady={handleGlobeReady}
        width={size.width}
        height={size.height}
        globeOffset={globeOffset}
        rendererConfig={{ antialias: true, alpha: false }}
        backgroundColor={globeTok.background}
        backgroundImageUrl={spaceImageUrl}
        globeImageUrl={surface.imageUrl}
        bumpImageUrl={surface.bumpUrl}
        globeMaterial={globeMaterial}
        showAtmosphere
        atmosphereColor={globeTok.atmosphere}
        atmosphereAltitude={globeTok.atmosphereAltitude}
        polygonsData={surface.features}
        polygonGeoJsonGeometry="geometry"
        polygonAltitude={globeTok.landAltitude}
        polygonCapColor={globeTok.landCap}
        polygonSideColor={globeTok.landSide}
        polygonStrokeColor={globeTok.landStroke}
        polygonsTransitionDuration={0}
        pointsData={markers}
        pointLat={(datum) => (datum as Marker).lat}
        pointLng={(datum) => (datum as Marker).lng}
        pointColor={(datum: object) => colorForMarker(datum as Marker)}
        pointAltitude={markerTok.altitude}
        pointRadius={(datum) =>
          (datum as Marker).id === SELECTED_MARKER_ID ? markerTok.selectedRadius : markerTok.radius
        }
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
        arcsData={edges}
        arcStartLat={(datum) => (datum as ResolvedEdge).startLat}
        arcStartLng={(datum) => (datum as ResolvedEdge).startLng}
        arcEndLat={(datum) => (datum as ResolvedEdge).endLat}
        arcEndLng={(datum) => (datum as ResolvedEdge).endLng}
        arcAltitude={arcTok.altitude}
        arcColor={(datum: object) =>
          (datum as ResolvedEdge).isSeaCrossing ? arcTok.sea : arcTok.land
        }
        arcStroke={arcTok.stroke}
        arcDashLength={arcTok.dashLength}
        arcDashGap={arcTok.dashGap}
        arcDashAnimateTime={arcTok.dashAnimateMs}
        arcsTransitionDuration={0}
      />

      <div className="sim-label-layer" aria-label="Map annotations">
        {labels.map((label) => (
          <div
            className="sim-anchor"
            data-label-kind={label.kind}
            key={label.id}
            ref={(element) => {
              label.anchorEl = element
            }}
          >
            <div
              className={`sim-label sim-label--${label.kind}${
                label.illustrative ? ' sim-label--illustrative' : ''
              }`}
              ref={(element) => {
                label.labelEl = element
              }}
            >
              {label.text}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** True when the camera-to-label segment passes through the globe sphere. */
function isOccluded(globe: GlobeMethods, label: LabelDatum): boolean {
  const point = globe.getCoords(label.lat, label.lng, label.alt)
  const camera = globe.camera().position
  const dx = point.x - camera.x
  const dy = point.y - camera.y
  const dz = point.z - camera.z
  const lengthSquared = dx * dx + dy * dy + dz * dz
  if (lengthSquared === 0) return false

  const t = -(camera.x * dx + camera.y * dy + camera.z * dz) / lengthSquared
  if (t <= 0 || t >= 1) return false
  const closestX = camera.x + dx * t
  const closestY = camera.y + dy * t
  const closestZ = camera.z + dz * t
  const closestSquared = closestX * closestX + closestY * closestY + closestZ * closestZ
  const radius = globe.getGlobeRadius() * 1.003
  return closestSquared < radius * radius
}
