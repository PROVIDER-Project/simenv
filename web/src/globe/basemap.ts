/**
 * Offline night-earth texture builder.
 *
 * Natural Earth country geometry provides the silhouette. A deterministic
 * canvas pass adds coastal light, clustered city sparkle and a separate bump
 * texture so the dark render retains the shallow relief visible in the white
 * skeleton reference. No remote tiles or imagery are required.
 */

export interface BasemapColors {
  ocean: string
  land: string
  coast: string
  cityLight: string
  cityWarm: string
}

type Position = [number, number]
type LinearRing = Position[]
type PolygonCoordinates = LinearRing[]
type MultiPolygonCoordinates = PolygonCoordinates[]

export interface GeoGeometry {
  type: 'Polygon' | 'MultiPolygon'
  coordinates: PolygonCoordinates | MultiPolygonCoordinates
}

export interface GeoFeature {
  type: 'Feature'
  geometry: GeoGeometry
}

interface FeatureCollectionInput {
  type: 'FeatureCollection'
  features: unknown[]
}

export interface BasemapTextures {
  color: HTMLCanvasElement
  bump: HTMLCanvasElement
}

interface LightCluster {
  lon: number
  lat: number
  spreadLon: number
  spreadLat: number
  count: number
}

const LIGHT_CLUSTERS: LightCluster[] = [
  { lon: -82, lat: 37, spreadLon: 19, spreadLat: 10, count: 430 },
  { lon: -99, lat: 20, spreadLon: 10, spreadLat: 6, count: 120 },
  { lon: -46, lat: -23, spreadLon: 13, spreadLat: 9, count: 340 },
  { lon: -59, lat: -34, spreadLon: 9, spreadLat: 7, count: 150 },
  { lon: -75, lat: -8, spreadLon: 6, spreadLat: 17, count: 110 },
  { lon: 8, lat: 50, spreadLon: 18, spreadLat: 8, count: 420 },
  { lon: 31, lat: 30, spreadLon: 12, spreadLat: 8, count: 110 },
  { lon: 78, lat: 23, spreadLon: 18, spreadLat: 12, count: 360 },
  { lon: 116, lat: 34, spreadLon: 19, spreadLat: 12, count: 390 },
  { lon: 138, lat: 36, spreadLon: 10, spreadLat: 9, count: 180 },
]

/** Validate and explicitly map the same-origin GeoJSON before renderer code sees it. */
export function parseFeatureCollection(input: unknown): GeoFeature[] {
  if (!isRecord(input) || input.type !== 'FeatureCollection' || !Array.isArray(input.features)) {
    throw new Error('World basemap must be a GeoJSON FeatureCollection')
  }

  const collection: FeatureCollectionInput = {
    type: 'FeatureCollection',
    features: input.features,
  }

  const features: GeoFeature[] = []
  for (const candidate of collection.features) {
    if (!isRecord(candidate) || candidate.type !== 'Feature' || !isRecord(candidate.geometry)) continue
    const geometry = mapGeometry(candidate.geometry)
    if (geometry) features.push({ type: 'Feature', geometry })
  }
  if (features.length === 0) throw new Error('World basemap contains no Polygon features')
  return features
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function mapGeometry(value: Record<string, unknown>): GeoGeometry | null {
  if (value.type === 'Polygon') {
    const coordinates = mapPolygon(value.coordinates)
    return coordinates ? { type: 'Polygon', coordinates } : null
  }
  if (value.type === 'MultiPolygon' && Array.isArray(value.coordinates)) {
    const coordinates: MultiPolygonCoordinates = []
    for (const polygonInput of value.coordinates) {
      const polygon = mapPolygon(polygonInput)
      if (!polygon) return null
      coordinates.push(polygon)
    }
    return coordinates.length > 0 ? { type: 'MultiPolygon', coordinates } : null
  }
  return null
}

function mapPolygon(value: unknown): PolygonCoordinates | null {
  if (!Array.isArray(value)) return null
  const polygon: PolygonCoordinates = []
  for (const ringInput of value) {
    if (!Array.isArray(ringInput)) return null
    const ring: LinearRing = []
    for (const positionInput of ringInput) {
      if (
        !Array.isArray(positionInput) ||
        positionInput.length < 2 ||
        typeof positionInput[0] !== 'number' ||
        typeof positionInput[1] !== 'number' ||
        !Number.isFinite(positionInput[0]) ||
        !Number.isFinite(positionInput[1])
      ) {
        return null
      }
      ring.push([positionInput[0], positionInput[1]])
    }
    if (ring.length >= 3) polygon.push(ring)
  }
  return polygon.length > 0 ? polygon : null
}

function project(lon: number, lat: number, w: number, h: number): [number, number] {
  return [((lon + 180) / 360) * w, ((90 - lat) / 180) * h]
}

function polygonsOf(geometry: GeoGeometry): MultiPolygonCoordinates {
  return geometry.type === 'Polygon'
    ? [geometry.coordinates as PolygonCoordinates]
    : (geometry.coordinates as MultiPolygonCoordinates)
}

function traceFeatures(
  ctx: CanvasRenderingContext2D,
  features: GeoFeature[],
  width: number,
  height: number,
): void {
  for (const feature of features) {
    for (const polygon of polygonsOf(feature.geometry)) {
      ctx.beginPath()
      for (const ring of polygon) {
        const lons = ring.map(([lon]) => lon)
        // Avoid dateline streaks; the tiny omitted islands do not affect the
        // reference-facing Atlantic composition.
        if (Math.max(...lons) - Math.min(...lons) > 180) continue
        ring.forEach(([lon, lat], index) => {
          const [x, y] = project(lon, lat, width, height)
          if (index === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        })
        ctx.closePath()
      }
      ctx.fill('evenodd')
      ctx.stroke()
    }
  }
}

function seededRandom(seed = 0x23b4): () => number {
  let state = seed >>> 0
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0
    return state / 0x1_0000_0000
  }
}

function bell(random: () => number): number {
  return (random() + random() + random() + random() - 2) / 2
}

function paintLight(
  ctx: CanvasRenderingContext2D,
  bumpCtx: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  warm: boolean,
  colors: BasemapColors,
): void {
  ctx.fillStyle = warm ? colors.cityWarm : colors.cityLight
  ctx.globalAlpha = 0.34 + radius * 0.34
  ctx.fillRect(x, y, Math.max(0.55, radius), Math.max(0.55, radius))

  bumpCtx.fillStyle = radius > 1 ? '#C8C8C8' : '#989898'
  bumpCtx.globalAlpha = 0.85
  bumpCtx.fillRect(x, y, Math.max(1, radius), Math.max(1, radius))
}

/** Build colour + bump maps at a 2:1 equirectangular aspect ratio. */
export function buildBasemapTextures(
  features: GeoFeature[],
  colors: BasemapColors,
  width = 2048,
): BasemapTextures | null {
  const height = width / 2
  const colorCanvas = document.createElement('canvas')
  const bumpCanvas = document.createElement('canvas')
  const maskCanvas = document.createElement('canvas')
  for (const canvas of [colorCanvas, bumpCanvas, maskCanvas]) {
    canvas.width = width
    canvas.height = height
  }

  const ctx = colorCanvas.getContext('2d')
  const bumpCtx = bumpCanvas.getContext('2d')
  const maskCtx = maskCanvas.getContext('2d')
  if (!ctx || !bumpCtx || !maskCtx) return null

  ctx.fillStyle = colors.ocean
  ctx.fillRect(0, 0, width, height)
  ctx.fillStyle = colors.land
  ctx.strokeStyle = colors.coast
  ctx.lineWidth = 1.15
  ctx.lineJoin = 'round'
  ctx.shadowColor = colors.coast
  ctx.shadowBlur = 3
  traceFeatures(ctx, features, width, height)
  ctx.shadowBlur = 0

  bumpCtx.fillStyle = '#080808'
  bumpCtx.fillRect(0, 0, width, height)
  bumpCtx.fillStyle = '#505050'
  bumpCtx.strokeStyle = '#777777'
  bumpCtx.lineWidth = 1.5
  traceFeatures(bumpCtx, features, width, height)

  maskCtx.fillStyle = '#000000'
  maskCtx.fillRect(0, 0, width, height)
  maskCtx.fillStyle = '#FFFFFF'
  maskCtx.strokeStyle = '#FFFFFF'
  maskCtx.lineWidth = 1
  traceFeatures(maskCtx, features, width, height)
  const mask = maskCtx.getImageData(0, 0, width, height).data

  const random = seededRandom()
  const isLand = (x: number, y: number) => {
    const safeX = ((Math.round(x) % width) + width) % width
    const safeY = Math.max(0, Math.min(height - 1, Math.round(y)))
    return mask[(safeY * width + safeX) * 4] > 0
  }

  // A faint global dusting keeps smaller inhabited land from reading as empty.
  for (let index = 0; index < 1700; index += 1) {
    const x = random() * width
    const y = random() * height
    if (!isLand(x, y)) continue
    paintLight(ctx, bumpCtx, x, y, 0.45 + random() * 0.55, random() > 0.82, colors)
  }

  // Seeded population-like clusters create the city-light rhythm of the dark
  // reference without pretending to be a GIS population dataset.
  for (const cluster of LIGHT_CLUSTERS) {
    for (let index = 0; index < cluster.count; index += 1) {
      const lon = cluster.lon + bell(random) * cluster.spreadLon
      const lat = cluster.lat + bell(random) * cluster.spreadLat
      const [x, y] = project(lon, lat, width, height)
      if (!isLand(x, y)) continue
      paintLight(ctx, bumpCtx, x, y, 0.6 + random() * 1.15, random() > 0.72, colors)
    }
  }

  ctx.globalAlpha = 1
  bumpCtx.globalAlpha = 1
  return { color: colorCanvas, bump: bumpCanvas }
}

/** Deterministic sparse stars + a cyan ambient field for the WebGL backdrop. */
export function buildSpaceCanvas(width = 1600, height = 1000): HTMLCanvasElement | null {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return null

  ctx.fillStyle = '#02050C'
  ctx.fillRect(0, 0, width, height)
  const glow = ctx.createRadialGradient(width * 0.5, height * 0.47, 30, width * 0.5, height * 0.47, width * 0.42)
  glow.addColorStop(0, 'rgba(38, 118, 174, 0.19)')
  glow.addColorStop(0.48, 'rgba(12, 52, 84, 0.10)')
  glow.addColorStop(1, 'rgba(2, 5, 12, 0)')
  ctx.fillStyle = glow
  ctx.fillRect(0, 0, width, height)

  const random = seededRandom(0x517a)
  for (let index = 0; index < 260; index += 1) {
    const x = random() * width
    const y = random() * height
    const radius = random() > 0.93 ? 1.1 : 0.45
    ctx.fillStyle = `rgba(188, 226, 255, ${0.12 + random() * 0.42})`
    ctx.beginPath()
    ctx.arc(x, y, radius, 0, Math.PI * 2)
    ctx.fill()
  }
  return canvas
}
