// localStorage that never throws (private mode, blocked storage, quota).

export function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw === null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage unavailable; the app still works without it */
  }
}

export function readString(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeString(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* ignore */
  }
}

export const KEYS = {
  area: 'cloudsea.area',
  photos: 'cloudsea.photos',
  going: 'cloudsea.going',
} as const

export interface StoredPhoto {
  id: string
  token: string
  /** IST date of the upload, used to show recent photos first. */
  date?: string
}
