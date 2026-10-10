import type { Backtest } from '../types'

type Bin = Backtest['calibration'][number]

const W = 320
const H = 270
const M = { left: 44, right: 14, top: 12, bottom: 44 }
const PW = W - M.left - M.right
const PH = H - M.top - M.bottom
const x = (p: number) => M.left + p * PW
const y = (p: number) => M.top + (1 - p) * PH
const TICKS = [0, 0.25, 0.5, 0.75, 1]
const pctLabel = (p: number) => `${Math.round(p * 100)}%`

/** Predicted vs observed, one dot per bin, with the diagonal as reference. */
export function CalibrationChart({ bins }: { bins: Bin[] }) {
  if (bins.length === 0) return null
  const maxN = Math.max(...bins.map((b) => b.n), 1)
  const r = (n: number) => 4 + 5 * Math.sqrt(n / maxN)
  const pts = [...bins].sort((a, b) => a.predicted - b.predicted)
  const path = pts.map((b, i) => `${i ? 'L' : 'M'}${x(b.predicted).toFixed(1)},${y(b.observed).toFixed(1)}`).join('')
  const angle = (-Math.atan2(PH, PW) * 180) / Math.PI

  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="cal-title cal-desc">
        <title id="cal-title">Calibration: forecast chance against how often a cloud sea happened</title>
        <desc id="cal-desc">
          {pts.map((b) => `${b.bin}: forecast ${pctLabel(b.predicted)}, happened ${pctLabel(b.observed)}, ${b.n} mornings.`).join(' ')}
        </desc>
        {TICKS.map((t) => (
          <g key={t}>
            <line className="cal-grid" x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} />
            <text className="cal-tick" x={M.left - 6} y={y(t)} dy="0.32em" textAnchor="end">
              {pctLabel(t)}
            </text>
            <text className="cal-tick" x={x(t)} y={y(0) + 16} textAnchor="middle">
              {pctLabel(t)}
            </text>
          </g>
        ))}
        <line className="cal-axis" x1={x(0)} x2={x(1)} y1={y(0)} y2={y(0)} />
        <line className="cal-diag" x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} />
        <text className="cal-note" transform={`translate(${x(0.58)},${y(0.58)}) rotate(${angle.toFixed(1)})`} dy="-7" textAnchor="middle">
          Perfectly calibrated
        </text>
        <path className="cal-line" d={path} />
        {pts.map((b) => (
          <g key={b.bin} className="cal-pt">
            <title>{`${b.bin}: forecast ${pctLabel(b.predicted)}, happened ${pctLabel(b.observed)} (${b.n} mornings)`}</title>
            <circle className="cal-hit" cx={x(b.predicted)} cy={y(b.observed)} r={14} />
            <circle className="cal-dot" cx={x(b.predicted)} cy={y(b.observed)} r={r(b.n)} />
          </g>
        ))}
        <text className="cal-label" x={x(0.5)} y={H - 6} textAnchor="middle">
          Forecast chance of a cloud sea
        </text>
        <text className="cal-label" transform={`translate(11,${y(0.5)}) rotate(-90)`} textAnchor="middle">
          How often it happened
        </text>
      </svg>
      <figcaption className="caption">
        Each dot is a group of mornings with a similar forecast; bigger dots hold more mornings. Dots near the dashed line
        mean the percentages can be taken at face value.
      </figcaption>
      <details className="table-toggle">
        <summary>Show as a table</summary>
        <table className="data">
          <thead>
            <tr>
              <th scope="col">Forecast</th>
              <th scope="col">Average forecast</th>
              <th scope="col">Happened</th>
              <th scope="col">Mornings</th>
            </tr>
          </thead>
          <tbody>
            {pts.map((b) => (
              <tr key={b.bin}>
                <th scope="row">{b.bin}</th>
                <td>{pctLabel(b.predicted)}</td>
                <td>{pctLabel(b.observed)}</td>
                <td>{b.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  )
}
