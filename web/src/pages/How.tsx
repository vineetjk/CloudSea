import { getBacktest } from '../api'
import { Loading } from '../components/Chrome'
import type { Backtest } from '../types'
import { useLoad } from '../useLoad'
import { CalibrationChart } from './CalibrationChart'

export default function How() {
  return (
    <div className="stack prose">
      <div className="page-head">
        <h1>How it works</h1>
        <p className="lede">
          Each night CloudSea answers one question: at sunrise tomorrow, will the top of Nandi Hills (1478 m) be above a
          layer of cloud?
        </p>
      </div>

      <section className="card" aria-labelledby="data-h">
        <h2 id="data-h" className="card-title">
          The data
        </h2>
        <p>
          Half-hourly weather reports (METARs) from Kempegowda International Airport (VOBL) since 2011, from the Iowa
          Environmental Mesonet archive. They record fog, mist and low cloud at dawn. Weather model forecasts come from
          Open-Meteo. The forecast only uses information that is available by 8:30 PM the night before.
        </p>
      </section>

      <section className="card" aria-labelledby="forecast-h">
        <h2 id="forecast-h" className="card-title">
          The forecast
        </h2>
        <p>
          TabPFN, a pretrained model for tabular data from Prior Labs, turns tonight's readings into a probability of a cloud
          sea at sunrise. The probability sets the call: GO when a cloud sea is likely, MAYBE when it's a real
          possibility, SKIP when it's unlikely.
        </p>
      </section>

      <section className="card" aria-labelledby="gemma-h">
        <h2 id="gemma-h" className="card-title">
          The words and the photos
        </h2>
        <p>
          Gemma 4, an open model from Google (Apache 2.0), writes the short call from the forecast numbers. Every number
          it writes is checked against the forecast; if a check fails, a plain template is used instead.
        </p>
        <p>
          Gemma also rates sunrise photos from the summit. The person who took the photo confirms or corrects the
          rating with one tap, and only confirmed labels count.
        </p>
      </section>

      <section className="card" aria-labelledby="grade-h">
        <h2 id="grade-h" className="card-title">
          The grade
        </h2>
        <p>
          Every morning at 8:15 AM the night's call is graded against the airport's dawn reports and any confirmed
          summit photos. The result goes on the <a href="#/scoreboard">scoreboard</a>, misses included.
        </p>
      </section>

      <section className="card" aria-labelledby="limits-h">
        <h2 id="limits-h" className="card-title">
          The limits
        </h2>
        <ul className="plain-list">
          <li>
            The airport is about 20 km away and 563 m lower than the summit. Fog at the airport doesn't always mean a
            cloud sea at the top.
          </li>
          <li>
            Nobody measures the height of the cloud tops. If the cloud is thick, the summit sits inside it and there's
            no view at all.
          </li>
          <li>Weather models can be wrong the night before, and a few weeks of live grading is not much evidence yet.</li>
        </ul>
      </section>

      <BacktestSection />

      <section className="card" aria-labelledby="credits-h">
        <h2 id="credits-h" className="card-title">
          Credits
        </h2>
        <ul className="plain-list">
          <li>
            <a href="https://open-meteo.com/">Weather data by Open-Meteo.com</a> (CC BY 4.0)
          </li>
          <li>
            Airport reports via <a href="https://mesonet.agron.iastate.edu/">Iowa Environmental Mesonet</a>
          </li>
          <li>Forecast by TabPFN (Prior Labs)</li>
          <li>Call text and photo ratings by Gemma 4 (Apache 2.0)</li>
          <li>
            Open source: <a href="https://github.com/vineetjk/CloudSea">github.com/vineetjk/CloudSea</a>
          </li>
        </ul>
      </section>
    </div>
  )
}

function BacktestSection() {
  const [state] = useLoad(getBacktest)
  return (
    <section className="card" aria-labelledby="backtest-h">
      <h2 id="backtest-h" className="card-title">
        Backtest
      </h2>
      {state.status === 'loading' && <Loading label="Loading the backtest" />}
      {state.status === 'error' && <p className="muted">Backtest results aren't available right now.</p>}
      {state.status === 'ok' && <BacktestView bt={state.data} />}
    </section>
  )
}

const two = (v: number) => v.toFixed(2)

function BacktestView({ bt }: { bt: Backtest }) {
  const h = bt.headline
  return (
    <>
      <p className="backtest-headline">
        In the {bt.season.replace('-', '–')} season, going every one of {h.weekends} weekends would have found a cloud
        sea {h.every_weekend_seas} {h.every_weekend_seas === 1 ? 'time' : 'times'}. Going only when CloudSea said GO
        would have meant {h.cloudsea_trips} {h.cloudsea_trips === 1 ? 'trip' : 'trips'} and {h.cloudsea_seas}{' '}
        {h.cloudsea_seas === 1 ? 'cloud sea' : 'cloud seas'}.
      </p>
      <p className="muted small">
        This is a backtest on a past season, run the way the live forecast runs. It is not a live result; the live
        record is on the scoreboard.
      </p>

      <div className="table-wrap">
        <table className="data">
          <caption className="sr-only">Backtest metrics by model</caption>
          <thead>
            <tr>
              <th scope="col">Model</th>
              <th scope="col">
                Brier <span className="th-note">lower is better</span>
              </th>
              <th scope="col">
                ROC AUC <span className="th-note">higher is better</span>
              </th>
              <th scope="col">
                GO precision <span className="th-note">GO calls with a sea</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {bt.metrics.map((m) => (
              <tr key={m.model}>
                <th scope="row">{m.model}</th>
                <td>{two(m.brier)}</td>
                <td>{two(m.roc_auc)}</td>
                <td>{m.go_precision === null ? '–' : `${Math.round(m.go_precision * 100)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className="sub-title">Calibration</h3>
      <CalibrationChart bins={bt.calibration} />
    </>
  )
}
