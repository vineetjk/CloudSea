// Pure rules for the sunrise-photo upload: the dawn window in IST, distance
// from the summit, and the resize-until-small-enough loop. No DOM here, so
// it runs under Vitest in Node. See docs/API.md, POST /api/photos.

import { IST_OFFSET_MIN, clock12, formatIstIso, istParts, shortDate } from './dates'

export const SUMMIT = { lat: 13.3702, lon: 77.6835 }
export const MAX_DISTANCE_KM = 3
export const WINDOW_START_S = 5 * 3600 // 05:00 IST
export const WINDOW_END_S = 8 * 3600 + 30 * 60 // 08:30 IST

export const MAX_EDGE = 1280
export const MAX_BYTES = 200 * 1024
export const QUALITY_STEPS = [0.85, 0.78, 0.71, 0.64, 0.57, 0.5]

export interface LatLon {
  lat: number
  lon: number
}

export function haversineKm(a: LatLon, b: LatLon): number {
  const R = 6371.0088
  const rad = Math.PI / 180
  const dLat = (b.lat - a.lat) * rad
  const dLon = (b.lon - a.lon) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)))
}

/** "+05:30" -> 330, "-03:00" -> -180, anything else -> null. */
export function parseOffset(raw: unknown): number | null {
  if (typeof raw !== 'string') return null
  const m = /^([+-])(\d{2}):?(\d{2})$/.exec(raw.trim())
  if (!m) return null
  return (m[1] === '-' ? -1 : 1) * (+m[2] * 60 + +m[3])
}

/**
 * EXIF DateTimeOriginal ("2026:10:11 06:05:12") -> epoch ms.
 * EXIF stores the camera's wall-clock time with no zone. If OffsetTimeOriginal
 * is present we use it; otherwise we assume the camera was on IST, which is
 * true for a phone at Nandi Hills.
 */
export function parseExifDate(raw: unknown, offset?: unknown): number | null {
  if (typeof raw !== 'string') return null
  const m = /^(\d{4})[:-](\d{2})[:-](\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/.exec(raw.trim())
  if (!m) return null
  const [y, mo, d, h, mi, s] = m.slice(1).map((v) => (v === undefined ? 0 : +v))
  if (y < 1990 || mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || s > 59) return null
  const offMin = parseOffset(offset) ?? IST_OFFSET_MIN
  return Date.UTC(y, mo - 1, d, h, mi, s) - offMin * 60_000
}

function dmsToDecimal(value: unknown, ref: unknown): number | null {
  let deg: number | null = null
  if (typeof value === 'number') deg = value
  else if (Array.isArray(value) && value.length >= 1 && value.every((v) => typeof v === 'number')) {
    const [d, m = 0, s = 0] = value as number[]
    deg = d + m / 60 + s / 3600
  }
  if (deg === null || !Number.isFinite(deg)) return null
  return ref === 'S' || ref === 'W' ? -Math.abs(deg) : deg
}

/** GPS position from exifr output, or null if missing or a 0,0 placeholder. */
export function gpsFromExif(exif: Record<string, unknown>): LatLon | null {
  let lat = typeof exif.latitude === 'number' ? exif.latitude : null
  let lon = typeof exif.longitude === 'number' ? exif.longitude : null
  if (lat === null || lon === null) {
    lat = dmsToDecimal(exif.GPSLatitude, exif.GPSLatitudeRef)
    lon = dmsToDecimal(exif.GPSLongitude, exif.GPSLongitudeRef)
  }
  if (lat === null || lon === null) return null
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null
  if (lat === 0 && lon === 0) return null
  return { lat, lon }
}

export type PhotoCheck =
  | { ok: true; takenAt: string; gpsPresent: boolean; distanceKm: number | null }
  | { ok: false; reason: 'no_time' | 'not_today' | 'outside_window' | 'too_far'; message: string }

const WINDOW_TEXT = 'between 5:00 and 8:30 AM'

/** Applies the client-side rules from docs/API.md to exifr output. */
export function checkPhoto(exif: Record<string, unknown> | null | undefined, nowMs: number): PhotoCheck {
  const taken = exif ? parseExifDate(exif.DateTimeOriginal, exif.OffsetTimeOriginal) : null
  if (taken === null) {
    return {
      ok: false,
      reason: 'no_time',
      message:
        "This photo doesn't carry its original capture time, so we can't tell it was taken at sunrise today. " +
        'Some apps remove it, for example WhatsApp, screenshots and some editors. ' +
        'Please pick the original photo from your camera or gallery.',
    }
  }
  const shot = istParts(taken)
  const today = istParts(nowMs).date
  if (shot.date !== today) {
    return {
      ok: false,
      reason: 'not_today',
      message: `This photo was taken on ${shortDate(shot.date)}. We can only use photos taken this morning, ${WINDOW_TEXT}.`,
    }
  }
  if (shot.seconds < WINDOW_START_S || shot.seconds > WINDOW_END_S) {
    return {
      ok: false,
      reason: 'outside_window',
      message: `This photo was taken at ${clock12(shot.seconds)}. We can only use photos taken around sunrise, ${WINDOW_TEXT}.`,
    }
  }
  const gps = exif ? gpsFromExif(exif) : null
  let distanceKm: number | null = null
  if (gps) {
    distanceKm = haversineKm(gps, SUMMIT)
    if (distanceKm > MAX_DISTANCE_KM) {
      return {
        ok: false,
        reason: 'too_far',
        message: `This photo's location is ${distanceKm.toFixed(1)} km from the Nandi Hills summit. We can only use photos taken within ${MAX_DISTANCE_KM} km of the top.`,
      }
    }
  }
  return { ok: true, takenAt: formatIstIso(taken), gpsPresent: gps !== null, distanceKm }
}

/** Scales (w, h) down so the long edge is at most maxEdge. Never scales up. */
export function fitWithin(width: number, height: number, maxEdge: number): { width: number; height: number } {
  const long = Math.max(width, height)
  if (long <= maxEdge) return { width, height }
  const k = maxEdge / long
  return { width: Math.max(1, Math.round(width * k)), height: Math.max(1, Math.round(height * k)) }
}

export class PhotoTooLargeError extends Error {
  constructor() {
    super("We couldn't make this photo small enough to upload. Please try a different photo.")
  }
}

/**
 * Calls encode(quality, maxEdge) with quality stepping down 0.85 -> 0.5 until
 * the result is <= maxBytes. If the lowest quality is still too big, it tries
 * a smaller long edge. Returns the first result that fits.
 */
export async function encodeUnderLimit<T extends { size: number }>(
  encode: (quality: number, maxEdge: number) => Promise<T>,
  {
    maxBytes = MAX_BYTES,
    edges = [MAX_EDGE, 1024, 800],
    qualities = QUALITY_STEPS,
  }: { maxBytes?: number; edges?: number[]; qualities?: number[] } = {},
): Promise<{ output: T; quality: number; maxEdge: number }> {
  for (const maxEdge of edges) {
    for (const quality of qualities) {
      const output = await encode(quality, maxEdge)
      if (output.size <= maxBytes) return { output, quality, maxEdge }
    }
  }
  throw new PhotoTooLargeError()
}
