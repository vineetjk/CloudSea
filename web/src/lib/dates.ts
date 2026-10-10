// Date helpers. Everything here works in IST (Asia/Kolkata, UTC+05:30, no DST)
// by explicit offset arithmetic, so the device's own time zone never matters.

export const IST_OFFSET_MIN = 330

const DAYS_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const DAYS_LONG = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const pad = (n: number) => String(n).padStart(2, '0')

/** "2026-10-11" -> UTC midnight of that calendar date, or null. */
function ymdToUtc(ymd: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd)
  if (!m) return null
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]))
}

/** "Sun 11 Oct" */
export function shortDate(ymd: string): string {
  const d = ymdToUtc(ymd)
  if (!d) return ymd
  return `${DAYS_SHORT[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`
}

/** "Sunday 11 Oct" */
export function longDate(ymd: string): string {
  const d = ymdToUtc(ymd)
  if (!d) return ymd
  return `${DAYS_LONG[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`
}

/** "30 Sep 2025" */
export function dayMonthYear(ymd: string): string {
  const d = ymdToUtc(ymd)
  if (!d) return ymd
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

export function addDays(ymd: string, days: number): string {
  const d = ymdToUtc(ymd)
  if (!d) return ymd
  d.setUTCDate(d.getUTCDate() + days)
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`
}

export interface IstParts {
  /** Calendar date in IST, "YYYY-MM-DD". */
  date: string
  /** Seconds since IST midnight. */
  seconds: number
}

export function istParts(epochMs: number): IstParts {
  const d = new Date(epochMs + IST_OFFSET_MIN * 60_000)
  return {
    date: `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`,
    seconds: d.getUTCHours() * 3600 + d.getUTCMinutes() * 60 + d.getUTCSeconds(),
  }
}

/** 30600 -> "8:30 AM" */
export function clock12(secondsOfDay: number): string {
  const h = Math.floor(secondsOfDay / 3600) % 24
  const m = Math.floor((secondsOfDay % 3600) / 60)
  return `${h % 12 === 0 ? 12 : h % 12}:${pad(m)} ${h < 12 ? 'AM' : 'PM'}`
}

/** An ISO timestamp with any offset -> its IST clock time, "8:30 PM". */
export function istClock12(iso: string): string {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  return clock12(istParts(t).seconds)
}

/** Epoch ms -> "2026-10-11T06:05:00+05:30" */
export function formatIstIso(epochMs: number): string {
  const d = new Date(epochMs + IST_OFFSET_MIN * 60_000)
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}+05:30`
  )
}

/** "06:09" -> seconds since midnight, or null. */
export function hhmmToSeconds(hhmm: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm)
  return m ? +m[1] * 3600 + +m[2] * 60 : null
}
