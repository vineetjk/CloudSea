import type { Backtest, Photo, PhotoLabel, Scoreboard, TodayResponse, UploadResponse } from './types'

export const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/+$/, '')
export const MOCK = import.meta.env.VITE_MOCK === '1'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  if (MOCK) {
    const { mockFetch } = await import('./mocks/mockApi')
    return mockFetch(path, init)
  }
  return fetch(API_BASE + path, init)
}

function fallbackMessage(status: number): string {
  if (status === 413) return 'That photo is too large to upload.'
  if (status === 429) return "You've reached today's limit. Please try again tomorrow."
  if (status === 404) return "We couldn't find that."
  return 'Something went wrong on our side. Please try again in a minute.'
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await request(path, init)
  } catch {
    throw new ApiError(0, "We couldn't reach CloudSea. Check your connection and try again.")
  }
  if (!res.ok) {
    let message = ''
    try {
      const body = (await res.json()) as { error?: unknown }
      if (typeof body.error === 'string') message = body.error
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message || fallbackMessage(res.status))
  }
  return (await res.json()) as T
}

const postJson = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const getToday = () => call<TodayResponse>('/api/today')
export const getScoreboard = () => call<Scoreboard>('/api/scoreboard')
export const getBacktest = () => call<Backtest>('/api/backtest')

export const postGoing = (date: string) => call<{ count: number }>('/api/going', postJson({ date }))

export interface UploadFields {
  photo: Blob
  takenAt: string
  gpsPresent: boolean
  distanceKm: number | null
  isPublic: boolean
}

export function uploadPhoto(f: UploadFields): Promise<UploadResponse> {
  const form = new FormData()
  form.append('photo', f.photo, 'sunrise.jpg')
  form.append('taken_at', f.takenAt)
  form.append('gps_present', f.gpsPresent ? 'true' : 'false')
  if (f.gpsPresent && f.distanceKm !== null) form.append('distance_km', f.distanceKm.toFixed(2))
  form.append('public', f.isPublic ? 'true' : 'false')
  return call<UploadResponse>('/api/photos', { method: 'POST', body: form })
}

export const getPhoto = (id: string, token: string) =>
  call<Photo>(`/api/photos/${encodeURIComponent(id)}?token=${encodeURIComponent(token)}`)

export const confirmPhoto = (id: string, token: string, label: PhotoLabel, isPublic: boolean) =>
  call<Photo>(`/api/photos/${encodeURIComponent(id)}/confirm`, postJson({ token, label, public: isPublic }))

/** Absolute origin for links that leave the app (share pages). */
function publicBase(): string {
  return /^https?:\/\//.test(API_BASE) ? API_BASE : location.origin + API_BASE
}

export const shareUrl = (date: string) => `${publicBase()}/s/${date}`
export const storyUrl = (date: string) => `${API_BASE}/story/${date}.png`
