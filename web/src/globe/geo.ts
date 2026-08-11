/**
 * Geographic helpers for placing annotations on the rendered globe.
 *
 * Edge-label placement is the non-obvious piece. globe.gl (three-globe) does NOT
 * draw an arc along the geographic great circle: it builds a cubic Bézier through
 * the great-circle points at t=0.25 and t=0.75, each lifted to 1.5× the arc's
 * apex altitude, from surface start to surface end. For a long arc at a small
 * fixed altitude the Bézier apex sinks below the surface and the middle of the
 * arc is occluded — so labels must anchor to the ACTUAL Bézier apex, not the
 * great-circle midpoint, and the arc altitude must scale with length.
 *
 * `arcApex` replicates three-globe's `calcCurve` exactly (same control-point
 * placement, altitude auto-scaling, and axis convention) and returns the apex as
 * lat/lng/alt, so a label anchored there sits on the rendered curve.
 */

export interface LatLng {
  lat: number
  lng: number
}

export interface Apex {
  lat: number
  lng: number
  alt: number
}

const DEG = Math.PI / 180

/** Wrap a longitude in degrees into the (-180, 180] range. */
function wrapLng(lng: number): number {
  return ((((lng + 180) % 360) + 360) % 360) - 180
}

type Vec3 = [number, number, number]

/** three-globe's polar→cartesian on a unit sphere (radius 1 + altitude). */
function polarToCartesian(lat: number, lng: number, alt: number): Vec3 {
  const phi = (90 - lat) * DEG
  const theta = (90 - lng) * DEG
  const r = 1 + alt
  const sinPhi = Math.sin(phi)
  return [r * sinPhi * Math.cos(theta), r * Math.cos(phi), r * sinPhi * Math.sin(theta)]
}

/** Inverse of `polarToCartesian`. */
function cartesianToPolar([x, y, z]: Vec3): Apex {
  const r = Math.hypot(x, y, z)
  const lat = 90 - (Math.acos(y / r) / DEG)
  const lng = wrapLng(90 - (Math.atan2(z, x) / DEG))
  return { lat, lng, alt: r - 1 }
}

function dot3(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

/** Great-circle (spherical) interpolation between two lat/lng points. */
function slerp(a: LatLng, b: LatLng, t: number): LatLng {
  const va = polarToCartesian(a.lat, a.lng, 0)
  const vb = polarToCartesian(b.lat, b.lng, 0)
  const omega = Math.acos(Math.max(-1, Math.min(1, dot3(va, vb))))
  if (omega === 0) return { lat: a.lat, lng: a.lng }
  const s1 = Math.sin((1 - t) * omega) / Math.sin(omega)
  const s2 = Math.sin(t * omega) / Math.sin(omega)
  const p = cartesianToPolar([
    s1 * va[0] + s2 * vb[0],
    s1 * va[1] + s2 * vb[1],
    s1 * va[2] + s2 * vb[2],
  ])
  return { lat: p.lat, lng: p.lng }
}

/**
 * The rendered apex of a globe.gl arc, replicating three-globe's `calcCurve`.
 *
 * `altitudeAutoScale` matches the `arcAltitudeAutoScale` set on the globe: with a
 * null arc altitude, three-globe uses `geoDistance/2 * autoScale`. Control points
 * sit at the great-circle 0.25/0.75 points lifted to 1.5× that altitude; the apex
 * is the cubic Bézier evaluated at t=0.5.
 */
export function arcApex(a: LatLng, b: LatLng, altitudeAutoScale: number): Apex {
  const va = polarToCartesian(a.lat, a.lng, 0)
  const vb = polarToCartesian(b.lat, b.lng, 0)
  const angular = Math.acos(Math.max(-1, Math.min(1, dot3(va, vb))))
  const altitude = (angular / 2) * altitudeAutoScale
  const cpAlt = altitude + altitude * 0.5 // three-globe calcAltCp(0, altitude)

  const g025 = slerp(a, b, 0.25)
  const g075 = slerp(a, b, 0.75)
  const p0 = polarToCartesian(a.lat, a.lng, 0)
  const c1 = polarToCartesian(g025.lat, g025.lng, cpAlt)
  const c2 = polarToCartesian(g075.lat, g075.lng, cpAlt)
  const p3 = polarToCartesian(b.lat, b.lng, 0)

  // Cubic Bézier at t=0.5: 0.125·P0 + 0.375·C1 + 0.375·C2 + 0.125·P3.
  const mid: Vec3 = [
    0.125 * p0[0] + 0.375 * c1[0] + 0.375 * c2[0] + 0.125 * p3[0],
    0.125 * p0[1] + 0.375 * c1[1] + 0.375 * c2[1] + 0.125 * p3[1],
    0.125 * p0[2] + 0.375 * c1[2] + 0.375 * c2[2] + 0.125 * p3[2],
  ]
  return cartesianToPolar(mid)
}
