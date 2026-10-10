import type { AirportOutcome, PhotoLabel } from './types'

export { shortDate, longDate } from './lib/dates'

/** 0.083 -> 8 */
export const pct = (p: number) => Math.round(p * 100)

export const PHOTO_LABELS: Record<PhotoLabel, string> = {
  cloud_sea: 'Cloud sea',
  partial: 'Partial',
  clear_no_sea: 'Clear, no sea',
  socked_in: 'Inside the fog',
}

export const PHOTO_LABEL_ORDER: PhotoLabel[] = ['cloud_sea', 'partial', 'clear_no_sea', 'socked_in']

export const AIRPORT_LABELS: Record<AirportOutcome, string> = {
  cloud_sea: 'Sea likely',
  no_sea: 'No sea',
}

export function airportText(o: AirportOutcome | null): string {
  return o ? AIRPORT_LABELS[o] : 'Not graded yet'
}

export function photoText(o: PhotoLabel | null, count?: number): string {
  if (!o) return count ? `${plural(count, 'photo', 'photos')}, none confirmed yet` : 'No confirmed photos'
  return count ? `${PHOTO_LABELS[o]} (${count})` : PHOTO_LABELS[o]
}

export function correctText(c: boolean | null): { mark: string; text: string } {
  if (c === true) return { mark: '✓', text: 'Correct' }
  if (c === false) return { mark: '✗', text: 'Missed' }
  return { mark: '·', text: 'Not graded yet' }
}

export function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}
