// DEMO FIXTURES ONLY. Loaded only when VITE_MOCK=1; production builds without
// it never include this file. Nothing here is a real forecast or a real
// grade. The JSON files in this folder follow the shapes in docs/API.md.
//
// Pick a state with ?demo= in the page URL:
//   ?demo=skip (default)  a SKIP call with a missed MAYBE graded the day before
//   ?demo=go              a GO call in December
//   ?demo=none            no call yet, and an empty scoreboard

import todaySkip from './today-skip.json'
import todayGo from './today-go.json'
import todayNone from './today-none.json'
import scoreboard from './scoreboard.json'
import scoreboardEmpty from './scoreboard-empty.json'
import backtest from './backtest.json'
import type { Photo, PhotoLabel, TodayResponse } from '../types'

type Demo = 'skip' | 'go' | 'none'

function demo(): Demo {
  const v = new URLSearchParams(location.search).get('demo')
  return v === 'go' || v === 'none' ? v : 'skip'
}

const goingExtra = new Set<string>()
const photos = new Map<string, Photo & { token: string; polls: number }>()
let uploads = 0

const DEMO_RATING = {
  label: 'cloud_sea' as PhotoLabel,
  confidence: 0.95,
  evidence: 'A white layer fills the valleys below the viewpoint, and the far hills rise out of it.',
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function today(): TodayResponse {
  const fixture = (demo() === 'go' ? todayGo : demo() === 'none' ? todayNone : todaySkip) as TodayResponse
  const copy: TodayResponse = JSON.parse(JSON.stringify(fixture))
  if (copy.call && goingExtra.has(copy.call.date)) copy.call.going_count += 1
  return copy
}

export async function mockFetch(path: string, init: RequestInit = {}): Promise<Response> {
  await wait(250)
  const method = (init.method ?? 'GET').toUpperCase()
  const url = new URL(path, location.origin)
  const p = url.pathname

  if (method === 'GET' && p === '/api/today') return json(today())
  if (method === 'GET' && p === '/api/scoreboard') return json(demo() === 'none' ? scoreboardEmpty : scoreboard)
  if (method === 'GET' && p === '/api/backtest') return json(backtest)

  if (method === 'POST' && p === '/api/going') {
    const { date } = JSON.parse(String(init.body ?? '{}')) as { date: string }
    goingExtra.add(date)
    return json({ count: (today().call?.going_count ?? 0) })
  }

  if (method === 'POST' && p === '/api/photos') {
    const form = init.body as FormData
    const file = form.get('photo')
    if (!(file instanceof Blob)) return json({ error: 'No photo was attached.' }, 400)
    if (file.size > 250 * 1024) return json({ error: 'That photo is larger than 250 KB.' }, 413)
    if (++uploads > 5) return json({ error: "You've uploaded 5 photos today. Thank you; that's the daily limit." }, 429)
    const id = `p_demo${uploads}`
    photos.set(id, {
      id,
      token: `t_demo${uploads}`,
      date: String(form.get('taken_at') ?? '').slice(0, 10),
      status: 'queued',
      rating: null,
      confirmed_label: null,
      public: form.get('public') === 'true',
      polls: 0,
    })
    return json({ id, token: `t_demo${uploads}`, status: 'queued' }, 201)
  }

  const m = /^\/api\/photos\/([^/]+)(\/confirm)?$/.exec(p)
  if (m) {
    const id = m[1]
    let photo = photos.get(id)
    if (!photo && id.startsWith('p_demo')) {
      // A demo photo from before a page reload: show it as rated.
      photo = { id, token: '', date: '', status: 'rated', rating: DEMO_RATING, confirmed_label: null, public: false, polls: 1 }
      photos.set(id, photo)
    }
    if (!photo) return json({ error: 'Photo not found.' }, 404)

    if (method === 'GET') {
      // Queued on the first check, rated from the second.
      if (photo.polls++ >= 1 && photo.status === 'queued') {
        photo.status = 'rated'
        photo.rating = DEMO_RATING
      }
    } else if (method === 'POST' && m[2]) {
      const body = JSON.parse(String(init.body ?? '{}')) as { label: PhotoLabel; public: boolean }
      photo.confirmed_label = body.label
      photo.public = body.public
    }
    const { token: _t, polls: _p, ...out } = photo
    return json(out)
  }

  return json({ error: `No demo fixture for ${method} ${p}` }, 404)
}
