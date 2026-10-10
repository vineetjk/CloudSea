import { useState } from 'react'
import { ApiError, MOCK, getToday, postGoing, shareUrl, storyUrl } from '../api'
import { LoadError, Loading } from '../components/Chrome'
import { airportText, correctText, longDate, pct, photoText, plural, shortDate } from '../format'
import { addDays, dayMonthYear, hhmmToSeconds, istClock12, istParts } from '../lib/dates'
import { KEYS, readJson, readString, writeJson, writeString } from '../storage'
import type { Call, GradedCall } from '../types'
import { useLoad } from '../useLoad'

const DEFAULT_AREA = 'electronics-city'

export default function Home() {
  const [state, reload] = useLoad(getToday)
  if (state.status === 'loading') return <Loading label="Loading tonight's call" />
  if (state.status === 'error') return <LoadError message={state.error} onRetry={reload} />
  const { status, call, last_graded } = state.data
  if (status === 'no_call_yet' || !call) return <NoCall last={last_graded ?? null} />
  return <CallView call={call} last={last_graded ?? null} />
}

function CallView({ call, last }: { call: Call; last: GradedCall | null }) {
  // Demo fixtures have fixed dates, so in demo mode the clock is set to just
  // after the fixture was issued. Live, it's the real time.
  const now = MOCK ? Date.parse(call.issued_at) + 35 * 60_000 : Date.now()
  const ist = istParts(now)
  const sunriseS = hhmmToSeconds(call.sunrise) ?? 6 * 3600
  const past = call.date < ist.date || (call.date === ist.date && ist.seconds > sunriseS)
  const relative = past ? null : call.date === ist.date ? 'This morning' : call.date === addDays(ist.date, 1) ? 'Tomorrow' : null
  const issuedDate = istParts(Date.parse(call.issued_at)).date

  return (
    <div className="stack">
      <section className={`hero hero-${call.verdict.toLowerCase()}`} aria-labelledby="verdict">
        <p className="hero-date">
          {relative && <>{relative} · </>}
          {longDate(call.date)}
        </p>
        <h1 id="verdict" className="verdict">
          <span className="sr-only">Nandi Hills sunrise call: </span>
          {call.verdict}
        </h1>
        <p className="chance">
          <strong>{pct(call.probability)}%</strong> chance of a cloud sea
        </p>
        <dl className="times">
          <div>
            <dt>Sunrise</dt>
            <dd>{call.sunrise}</dd>
          </div>
          <div>
            <dt>First light</dt>
            <dd>{call.first_light}</dd>
          </div>
        </dl>
        {past && (
          <p className="stale">
            This was the call for {shortDate(call.date)}. The next call goes live at 8:30 PM IST.
          </p>
        )}
        <p className="issued">
          Issued {istClock12(call.issued_at)} IST{issuedDate !== ist.date && <>, {shortDate(issuedDate)}</>}
        </p>
      </section>

      <LeaveBy call={call} />

      <CallText call={call} />

      <div className="two-col">
        <section className="card" aria-labelledby="carry-h">
          <h2 id="carry-h" className="card-title">
            What to carry
          </h2>
          <ul className="ticks">
            {call.carry.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>

        <section className="card" aria-labelledby="top-h">
          <h2 id="top-h" className="card-title">
            At the top
          </h2>
          <ul className="plain">
            <li>About {call.conditions.summit_temp_c}°C</li>
            <li>Wind {call.conditions.wind_kmh} km/h</li>
            <li>{call.conditions.rain_last_24h ? 'Rain in the last 24 hours; paths may be slippery' : 'No rain in the last 24 hours'}</li>
            <li>Gate opens {call.gate.opens}</li>
          </ul>
          {!call.gate.verified && (
            <p className="gate-note">{call.gate.note || 'Gate time not yet verified. Check before you go.'}</p>
          )}
        </section>
      </div>

      <Going key={`${call.date}:${call.going_count}`} call={call} closed={past} />

      <GuaranteeNote />

      <Share call={call} />

      {last && <LastGraded g={last} />}

      <p className="footnote">
        Forecast by {call.model.forecaster}, trained on data through {dayMonthYear(call.model.trained_through)}. Call
        text by {call.model.writer}.
      </p>
    </div>
  )
}

function LeaveBy({ call }: { call: Call }) {
  const options = call.leave_by
  const [area, setArea] = useState(() => readString(KEYS.area) ?? DEFAULT_AREA)
  if (options.length === 0) return null
  const chosen =
    options.find((o) => o.area === area) ?? options.find((o) => o.area === DEFAULT_AREA) ?? options[0]

  return (
    <section className="card leave" aria-labelledby="leave-h">
      <h2 id="leave-h" className="card-title">
        {call.verdict === 'SKIP' ? 'If you go anyway' : 'When to leave'}
      </h2>
      <p className="leave-line">
        <span className="leave-label">Leave by</span> <strong className="leave-time">{chosen.leave_by}</strong>{' '}
        <label htmlFor="area" className="leave-label">
          from
        </label>{' '}
        <select
          id="area"
          value={chosen.area}
          onChange={(e) => {
            setArea(e.target.value)
            writeString(KEYS.area, e.target.value)
          }}
        >
          {options.map((o) => (
            <option key={o.area} value={o.area}>
              {o.label}
            </option>
          ))}
        </select>
      </p>
      <p className="muted">
        About {chosen.drive_minutes} min drive. Includes a {chosen.buffer_minutes} min safety buffer.
      </p>
    </section>
  )
}

type Lang = 'en' | 'kn' | 'hi'

function CallText({ call }: { call: Call }) {
  const [lang, setLang] = useState<Lang>('en')
  const texts: Array<[Lang, string, string | null]> = [
    ['en', 'English', call.text],
    ['kn', 'ಕನ್ನಡ', call.text_kn],
    ['hi', 'हिन्दी', call.text_hi],
  ]
  const available = texts.filter(([, , t]) => t)
  const shown = available.find(([l]) => l === lang) ?? available[0]

  return (
    <section className="card" aria-labelledby="text-h">
      <h2 id="text-h" className="card-title">
        The call
      </h2>
      {available.length > 1 && (
        <div className="lang" role="group" aria-label="Language">
          {available.map(([l, name]) => (
            <button key={l} type="button" className="chip-btn" aria-pressed={shown[0] === l} onClick={() => setLang(l)} lang={l}>
              {name}
            </button>
          ))}
        </div>
      )}
      <p className="call-text" lang={shown[0]}>
        {shown[2]}
      </p>
      <p className="caption">Written by Gemma 4 from the forecast.</p>
    </section>
  )
}

function goingText(n: number): string {
  if (n <= 0) return "No one has said they're going yet."
  return `${plural(n, 'person says', 'people say')} they're going.`
}

function Going({ call, closed }: { call: Call; closed: boolean }) {
  const [count, setCount] = useState(call.going_count)
  const [tapped, setTapped] = useState(() => readJson<string[]>(KEYS.going, []).includes(call.date))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function tap() {
    setBusy(true)
    setError(null)
    try {
      const res = await postGoing(call.date)
      setCount(res.count)
      setTapped(true)
      const dates = readJson<string[]>(KEYS.going, []).filter((d) => d !== call.date)
      writeJson(KEYS.going, [...dates, call.date].slice(-14))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That didn't save. Please try again.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card going" aria-labelledby="going-h">
      <h2 id="going-h" className="card-title">
        Going?
      </h2>
      <p aria-live="polite">{goingText(count)}</p>
      {!closed && (
        <button
          type="button"
          className={tapped ? 'btn btn-done' : 'btn btn-primary'}
          onClick={tap}
          disabled={tapped || busy}
        >
          {tapped ? "✓ You're going" : busy ? 'Saving…' : "I'm going"}
        </button>
      )}
      {tapped && !closed && <p className="muted">Thanks. Enjoy the sunrise, and add a photo from the top if you can.</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}

function GuaranteeNote() {
  return (
    <section className="card note" aria-labelledby="note-h">
      <h2 id="note-h" className="card-title">
        A forecast, not a guarantee.
      </h2>
      <p>
        Every morning at 8:15 AM the call is graded against airport fog reports and photos from the summit, and the
        result goes on the <a href="#/scoreboard">scoreboard</a>, misses included.
      </p>
    </section>
  )
}

function Share({ call }: { call: Call }) {
  const url = shareUrl(call.date)
  const text = `${call.verdict} · ${pct(call.probability)}% cloud sea at Nandi · ${shortDate(call.date)}.`
  const whatsapp = 'https://wa.me/?text=' + encodeURIComponent(`${text} ${url}`)
  const canShare = typeof navigator.share === 'function'

  async function share() {
    try {
      await navigator.share({ title: 'CloudSea', text, url })
    } catch {
      /* closed the share sheet */
    }
  }

  return (
    <section className="card" aria-labelledby="share-h">
      <h2 id="share-h" className="card-title">
        Share the call
      </h2>
      <div className="btn-row">
        <a className="btn" href={whatsapp} target="_blank" rel="noopener noreferrer">
          WhatsApp
        </a>
        {canShare && (
          <button type="button" className="btn" onClick={share}>
            Share…
          </button>
        )}
        <a className="btn" href={storyUrl(call.date)} download={`cloudsea-${call.date}-story.png`}>
          Download story image
        </a>
      </div>
    </section>
  )
}

function LastGraded({ g }: { g: GradedCall }) {
  const result = correctText(g.correct)
  return (
    <section className="card" aria-labelledby="last-h">
      <h2 id="last-h" className="card-title">
        Last call graded
      </h2>
      <p className="last-head">
        <span className={`chip chip-${g.verdict.toLowerCase()}`}>{g.verdict}</span>{' '}
        <span>
          {pct(g.probability)}% for {shortDate(g.date)}
        </span>
      </p>
      <dl className="facts">
        <div>
          <dt>Airport</dt>
          <dd>{airportText(g.airport_outcome)}</dd>
        </div>
        <div>
          <dt>Summit photos</dt>
          <dd>{photoText(g.photo_outcome)}</dd>
        </div>
        <div>
          <dt>Result</dt>
          <dd className={g.correct === true ? 'ok' : g.correct === false ? 'miss' : undefined}>
            <span aria-hidden="true">{result.mark}</span> {result.text}
          </dd>
        </div>
      </dl>
      <p>
        <a href="#/scoreboard">See every graded morning</a>
      </p>
    </section>
  )
}

function NoCall({ last }: { last: GradedCall | null }) {
  return (
    <div className="stack">
      <section className="hero hero-none" aria-labelledby="none-h">
        <p className="hero-date">Nandi Hills sunrise</p>
        <h1 id="none-h" className="none-title">
          No call yet
        </h1>
        <p>
          The call goes live at 8:30 PM IST each night: GO, MAYBE or SKIP for the next sunrise, with the sunrise time
          and when to leave.
        </p>
      </section>
      <GuaranteeNote />
      {last && <LastGraded g={last} />}
    </div>
  )
}
