// Response shapes from docs/API.md.

export type Verdict = 'GO' | 'MAYBE' | 'SKIP'
export type AirportOutcome = 'cloud_sea' | 'no_sea'
export type PhotoLabel = 'cloud_sea' | 'partial' | 'clear_no_sea' | 'socked_in'

export interface LeaveBy {
  area: string
  label: string
  drive_minutes: number
  buffer_minutes: number
  leave_by: string
}

export interface Call {
  date: string
  issued_at: string
  verdict: Verdict
  probability: number
  sunrise: string
  first_light: string
  text: string
  text_kn: string | null
  text_hi: string | null
  carry: string[]
  conditions: { summit_temp_c: number; wind_kmh: number; rain_last_24h: boolean }
  leave_by: LeaveBy[]
  gate: { opens: string; verified: boolean; note: string | null }
  model: { forecaster: string; writer: string; trained_through: string }
  going_count: number
}

export interface GradedCall {
  date: string
  verdict: Verdict
  probability: number
  airport_outcome: AirportOutcome | null
  photo_outcome: PhotoLabel | null
  correct: boolean | null
}

export interface TodayResponse {
  status: 'ok' | 'no_call_yet'
  call: Call | null
  last_graded?: GradedCall | null
}

export interface ScoreDay extends GradedCall {
  photos: number
  evidence: string | null
}

export interface Scoreboard {
  summary: {
    graded: number
    correct: number
    go_calls: number
    go_hits: number
    brier: number | null
    since: string | null
  }
  days: ScoreDay[]
  agreement: { days_with_both: number; airport_and_photos_agree: number }
}

export interface Backtest {
  season: string
  headline: {
    weekend_mornings: number; every_weekend_seas: number; go_trips: number; go_seas: number
    go_or_maybe_trips: number; go_or_maybe_seas: number; seas_missed_by_skip: number
  }
  metrics: Array<{ model: string; brier: number; roc_auc: number; go_precision: number | null }>
  calibration: Array<{ bin: string; predicted: number; observed: number; n: number }>
}

export type PhotoStatus = 'queued' | 'rated' | 'failed'

export interface UploadResponse {
  id: string
  token: string
  status: PhotoStatus
}

export interface Photo {
  id: string
  date: string
  status: PhotoStatus
  rating: { label: PhotoLabel | 'unusable'; confidence: number; evidence: string } | null
  confirmed_label: PhotoLabel | null
  public: boolean
}
