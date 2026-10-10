import { describe, expect, it } from 'vitest'
import { istParts, shortDate, longDate, istClock12, addDays } from './dates'
import {
  SUMMIT,
  checkPhoto,
  encodeUnderLimit,
  fitWithin,
  gpsFromExif,
  haversineKm,
  parseExifDate,
  PhotoTooLargeError,
} from './photoRules'

// 2026-10-11 07:30 IST = 2026-10-11 02:00 UTC
const NOW = Date.UTC(2026, 9, 11, 2, 0, 0)

describe('haversineKm', () => {
  it('is zero at the same point', () => {
    expect(haversineKm(SUMMIT, SUMMIT)).toBe(0)
  })
  it('gives about 111.2 km for one degree of latitude', () => {
    expect(haversineKm({ lat: 13, lon: 77.6 }, { lat: 14, lon: 77.6 })).toBeCloseTo(111.2, 1)
  })
  it('puts Bengaluru airport (VOBL) about 20 km from the summit', () => {
    const d = haversineKm(SUMMIT, { lat: 13.1986, lon: 77.7066 })
    expect(d).toBeGreaterThan(18)
    expect(d).toBeLessThan(21)
  })
})

describe('parseExifDate', () => {
  it('treats a zone-less EXIF time as IST', () => {
    expect(parseExifDate('2026:10:11 06:05:00')).toBe(Date.UTC(2026, 9, 11, 0, 35, 0))
  })
  it('uses OffsetTimeOriginal when present', () => {
    expect(parseExifDate('2026:10:11 00:35:00', '+00:00')).toBe(Date.UTC(2026, 9, 11, 0, 35, 0))
    expect(parseExifDate('2026:10:10 21:05:00', '-03:30')).toBe(Date.UTC(2026, 9, 11, 0, 35, 0))
  })
  it('rejects missing or malformed values', () => {
    expect(parseExifDate(undefined)).toBeNull()
    expect(parseExifDate('0000:00:00 00:00:00')).toBeNull()
    expect(parseExifDate('yesterday')).toBeNull()
  })
})

describe('checkPhoto: dawn window in IST', () => {
  const at = (t: string, extra: Record<string, unknown> = {}) => checkPhoto({ DateTimeOriginal: t, ...extra }, NOW)

  it('accepts a photo from this morning and formats taken_at with +05:30', () => {
    expect(at('2026:10:11 06:12:30')).toEqual({
      ok: true,
      takenAt: '2026-10-11T06:12:30+05:30',
      gpsPresent: false,
      distanceKm: null,
    })
  })
  it('includes both ends of 05:00-08:30', () => {
    expect(at('2026:10:11 05:00:00').ok).toBe(true)
    expect(at('2026:10:11 08:30:00').ok).toBe(true)
    expect(at('2026:10:11 04:59:59')).toMatchObject({ ok: false, reason: 'outside_window' })
    expect(at('2026:10:11 08:30:01')).toMatchObject({ ok: false, reason: 'outside_window' })
  })
  it('says when a photo is from another day', () => {
    expect(at('2026:10:10 06:00:00')).toMatchObject({ ok: false, reason: 'not_today' })
    expect((at('2026:10:10 06:00:00') as { message: string }).message).toContain('Sat 10 Oct')
  })
  it('uses the IST date even when the UTC date is still yesterday', () => {
    // 00:15 IST on 11 Oct is 18:45 UTC on 10 Oct.
    const justAfterMidnight = Date.UTC(2026, 9, 10, 18, 45)
    expect(checkPhoto({ DateTimeOriginal: '2026:10:10 06:00:00' }, justAfterMidnight)).toMatchObject({
      reason: 'not_today',
    })
  })
  it('converts a non-IST camera offset before checking the window', () => {
    // 01:00 UTC is 06:30 IST.
    expect(at('2026:10:11 01:00:00', { OffsetTimeOriginal: '+00:00' })).toMatchObject({
      ok: true,
      takenAt: '2026-10-11T06:30:00+05:30',
    })
  })
  it('explains a missing capture time', () => {
    expect(checkPhoto({}, NOW)).toMatchObject({ ok: false, reason: 'no_time' })
    expect(checkPhoto(undefined, NOW)).toMatchObject({ ok: false, reason: 'no_time' })
  })
})

describe('checkPhoto: distance from the summit', () => {
  const base = { DateTimeOriginal: '2026:10:11 06:10:00' }
  it('accepts a photo within 3 km and reports the distance', () => {
    const r = checkPhoto({ ...base, latitude: 13.38, longitude: 77.69 }, NOW)
    expect(r.ok).toBe(true)
    if (r.ok) {
      expect(r.gpsPresent).toBe(true)
      expect(r.distanceKm).toBeLessThan(3)
    }
  })
  it('rejects a photo taken far from the summit', () => {
    const r = checkPhoto({ ...base, latitude: 12.9716, longitude: 77.5946 }, NOW)
    expect(r).toMatchObject({ ok: false, reason: 'too_far' })
  })
  it('reads degree/minute/second arrays with hemisphere refs', () => {
    expect(
      gpsFromExif({ GPSLatitude: [13, 22, 12.72], GPSLatitudeRef: 'N', GPSLongitude: [77, 41, 0.6], GPSLongitudeRef: 'E' }),
    ).toEqual({ lat: expect.closeTo(13.3702, 4), lon: expect.closeTo(77.6835, 4) })
    expect(gpsFromExif({ GPSLatitude: [33, 52, 0], GPSLatitudeRef: 'S', GPSLongitude: [151, 12, 0], GPSLongitudeRef: 'W' })).toEqual({
      lat: expect.closeTo(-33.8667, 3),
      lon: expect.closeTo(-151.2, 3),
    })
  })
  it('treats 0,0 as no GPS', () => {
    expect(gpsFromExif({ latitude: 0, longitude: 0 })).toBeNull()
    const r = checkPhoto({ ...base, latitude: 0, longitude: 0 }, NOW)
    expect(r).toMatchObject({ ok: true, gpsPresent: false })
  })
})

describe('fitWithin', () => {
  it('caps the long edge at 1280 and keeps the aspect ratio', () => {
    expect(fitWithin(4000, 3000, 1280)).toEqual({ width: 1280, height: 960 })
    expect(fitWithin(3000, 4000, 1280)).toEqual({ width: 960, height: 1280 })
  })
  it('never scales up', () => {
    expect(fitWithin(800, 600, 1280)).toEqual({ width: 800, height: 600 })
  })
})

describe('encodeUnderLimit', () => {
  // Fake encoder: size grows with quality and with the square of the edge.
  const fake = (bytesAt085: number) => {
    const calls: Array<[number, number]> = []
    const encode = async (q: number, edge: number) => {
      calls.push([q, edge])
      return { size: Math.round(bytesAt085 * (q / 0.85) * (edge / 1280) ** 2) }
    }
    return { calls, encode }
  }

  it('returns the first try when it already fits', async () => {
    const { calls, encode } = fake(150_000)
    const r = await encodeUnderLimit(encode)
    expect(r.quality).toBe(0.85)
    expect(r.maxEdge).toBe(1280)
    expect(calls).toHaveLength(1)
  })
  it('steps quality down until the result is at most 200 KB', async () => {
    const { calls, encode } = fake(300_000)
    const r = await encodeUnderLimit(encode)
    expect(r.output.size).toBeLessThanOrEqual(200 * 1024)
    expect(r.quality).toBe(0.57)
    expect(calls.map(([q]) => q)).toEqual([0.85, 0.78, 0.71, 0.64, 0.57])
  })
  it('shrinks the long edge when quality 0.5 is still too big', async () => {
    const { encode } = fake(500_000)
    const r = await encodeUnderLimit(encode)
    expect(r.maxEdge).toBe(1024)
    expect(r.output.size).toBeLessThanOrEqual(200 * 1024)
  })
  it('gives up with a friendly error if nothing fits', async () => {
    const { encode } = fake(50_000_000)
    await expect(encodeUnderLimit(encode)).rejects.toBeInstanceOf(PhotoTooLargeError)
  })
})

describe('date helpers', () => {
  it('formats dates without using the device time zone', () => {
    expect(shortDate('2026-10-11')).toBe('Sun 11 Oct')
    expect(longDate('2026-10-11')).toBe('Sunday 11 Oct')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
  })
  it('reads IST wall-clock time from an ISO timestamp', () => {
    expect(istClock12('2026-10-10T20:30:12+05:30')).toBe('8:30 PM')
    expect(istClock12('2026-10-10T15:00:00Z')).toBe('8:30 PM')
    expect(istParts(Date.UTC(2026, 9, 10, 18, 45)).date).toBe('2026-10-11')
  })
})
