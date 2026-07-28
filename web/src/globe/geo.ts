/**
 * Geographic helpers for placing annotations on the rendered globe.
 *
 * The one non-obvious piece is edge-label placement. globe.gl draws an arc whose
 * ground track is a GREAT CIRCLE and lifts it to `arcAltitude` at its midpoint.
 * So the visual apex of an arc is at:
 *   (great-circle midpoint lat/lng, altitude = arcAltitude)
 * NOT at the linear average of the two endpoints' lat/lng, and NOT at altitude 0.
 * `greatCircleMidpoint` gives the former; the caller supplies the arc altitude.
 */

export interface LatLng {
  lat: number
  lng: number
}

const toRad = (d: number): number => (d * Math.PI) / 180
const toDeg = (r: number): number => (r * 180) / Math.PI

/** Wrap a longitude in degrees into the (-180, 180] range. */
function wrapLng(lng: number): number {
  return ((((lng + 180) % 360) + 360) % 360) - 180
}

/**
 * Great-circle (spherical) midpoint of two lat/lng points, in degrees.
 *
 * Standard "intermediate point at fraction 0.5" reduced to the midpoint form.
 * This lies on the same great circle globe.gl draws the arc along, so a label
 * anchored here (at the arc's altitude) sits on the rendered curve.
 */
export function greatCircleMidpoint(a: LatLng, b: LatLng): LatLng {
  const lat1 = toRad(a.lat)
  const lon1 = toRad(a.lng)
  const lat2 = toRad(b.lat)
  const dLon = toRad(b.lng - a.lng)

  const bx = Math.cos(lat2) * Math.cos(dLon)
  const by = Math.cos(lat2) * Math.sin(dLon)

  const lat = Math.atan2(
    Math.sin(lat1) + Math.sin(lat2),
    Math.sqrt((Math.cos(lat1) + bx) ** 2 + by ** 2),
  )
  const lon = lon1 + Math.atan2(by, Math.cos(lat1) + bx)

  return { lat: toDeg(lat), lng: wrapLng(toDeg(lon)) }
}
