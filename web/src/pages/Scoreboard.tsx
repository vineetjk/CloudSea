import { getScoreboard } from '../api'
import { LoadError, Loading } from '../components/Chrome'
import { airportText, correctText, pct, photoText, plural, shortDate } from '../format'
import type { Scoreboard as Board } from '../types'
import { useLoad } from '../useLoad'

export default function Scoreboard() {
  const [state, reload] = useLoad(getScoreboard)
  return (
    <div className="stack">
      <div className="page-head">
        <h1>Scoreboard</h1>
        <p className="lede">Every morning CloudSea grades the night's call in public, right or wrong.</p>
      </div>
      {state.status === 'loading' && <Loading label="Loading the scoreboard" />}
      {state.status === 'error' && <LoadError message={state.error} onRetry={reload} />}
      {state.status === 'ok' && <BoardView board={state.data} />}
      <section className="card" aria-labelledby="grading-h">
        <h2 id="grading-h" className="card-title">
          How a morning is graded
        </h2>
        <p>
          Airport fog reports from Kempegowda International (VOBL) are a proxy. They show low cloud below summit height
          near the airport, not what people at the top saw. Summit photos, confirmed by the people who took them, are
          the ground truth when we have them. GO and MAYBE count as correct on a cloud sea; SKIP counts as correct when
          there was none.
        </p>
      </section>
    </div>
  )
}

function BoardView({ board }: { board: Board }) {
  const { summary, days, agreement } = board
  if (summary.graded === 0 || days.length === 0) {
    return (
      <div className="card empty">
        <p>The first graded morning appears here at 8:15 AM.</p>
      </div>
    )
  }

  return (
    <>
      <section aria-labelledby="summary-h">
        <h2 id="summary-h" className="sr-only">
          Summary
        </h2>
        <dl className="stats">
          <div>
            <dt>Mornings graded</dt>
            <dd>{summary.graded}</dd>
          </div>
          <div>
            <dt>Correct</dt>
            <dd>
              {summary.correct}
              <span className="of"> of {summary.graded}</span>
            </dd>
          </div>
          {summary.go_calls > 0 && (
            <div>
              <dt>GO calls with a sea</dt>
              <dd>
                {summary.go_hits}
                <span className="of"> of {summary.go_calls}</span>
              </dd>
            </div>
          )}
          {summary.brier !== null && (
            <div>
              <dt>Brier score</dt>
              <dd>{summary.brier.toFixed(2)}</dd>
            </div>
          )}
        </dl>
        <p className="muted small">
          {summary.since && <>Live calls since {shortDate(summary.since)}. </>}
          The Brier score measures how close the probabilities were to what happened: 0 is perfect, lower is better.
        </p>
        {agreement.days_with_both > 0 && (
          <p className="muted small">
            On {plural(agreement.days_with_both, 'morning', 'mornings')} with both airport reports and confirmed
            photos, they agreed {agreement.airport_and_photos_agree} {agreement.airport_and_photos_agree === 1 ? 'time' : 'times'}.
          </p>
        )}
      </section>

      <section aria-labelledby="days-h">
        <h2 id="days-h" className="section-title">
          Day by day
        </h2>
        <ol className="days">
          {days.map((d) => {
            const result = correctText(d.correct)
            return (
              <li key={d.date} className="day card">
                <div className="day-head">
                  <span className="day-date">{shortDate(d.date)}</span>
                  <span className={`chip chip-${d.verdict.toLowerCase()}`}>{d.verdict}</span>
                  <span className="day-pct">{pct(d.probability)}%</span>
                  <span
                    className={`day-result ${d.correct === true ? 'ok' : d.correct === false ? 'miss' : ''}`}
                  >
                    <span aria-hidden="true">{result.mark}</span> {result.text}
                  </span>
                </div>
                <dl className="facts">
                  <div>
                    <dt>Airport</dt>
                    <dd>{airportText(d.airport_outcome)}</dd>
                  </div>
                  <div>
                    <dt>Summit photos</dt>
                    <dd>{photoText(d.photo_outcome, d.photos)}</dd>
                  </div>
                </dl>
                {d.evidence && <p className="evidence">{d.evidence}</p>}
              </li>
            )
          })}
        </ol>
      </section>
    </>
  )
}
