import type { MouseEvent } from 'react'
import { MOCK } from '../api'
import { ROUTES, type Route } from '../router'

function focusMain(e: MouseEvent) {
  e.preventDefault()
  document.getElementById('main')?.focus()
}

export function Logo() {
  return (
    <svg className="logo" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <circle className="logo-sun" cx="16" cy="18" r="7" />
      <path
        className="logo-cloud"
        d="M2 22.5c0-2.6 2-4.6 4.5-4.6 1 0 1.9.3 2.6.8.8-1.9 2.7-3.2 4.9-3.2 2.4 0 4.4 1.5 5.1 3.6.6-.3 1.3-.5 2-.5 1.6 0 3 .9 3.7 2.2.5-.2 1-.3 1.6-.3 2 0 3.6 1.5 3.6 3.4V27H2z"
      />
    </svg>
  )
}

export function Header({ route }: { route: Route }) {
  return (
    <header className="site-header">
      <a className="skip-link" href="#/" onClick={focusMain}>
        Skip to content
      </a>
      <div className="container header-row">
        <a className="wordmark" href="#/">
          <Logo />
          <span>CloudSea</span>
        </a>
        {MOCK && (
          <span className="demo-badge" title="This page shows demo fixtures, not a live forecast.">
            Demo data
          </span>
        )}
      </div>
      <nav className="container" aria-label="Main">
        <ul className="nav">
          {ROUTES.map((r) => (
            <li key={r.route}>
              <a href={r.href} aria-current={route === r.route ? 'page' : undefined}>
                {r.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  )
}

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="container">
        <p className="footer-note">
          <strong>Forecast, not a guarantee.</strong> Every call is graded in public on the{' '}
          <a href="#/scoreboard">scoreboard</a>.
        </p>
        <p className="attrib">
          <a href="https://open-meteo.com/">Weather data by Open-Meteo.com</a> · Airport reports via{' '}
          <a href="https://mesonet.agron.iastate.edu/">Iowa Environmental Mesonet</a> · Forecast by TabPFN (Prior Labs) ·
          Call text and photo ratings by Gemma 4 (Apache 2.0)
        </p>
        <p className="attrib">
          <a href="https://github.com/vineetjk/CloudSea">Source code on GitHub</a>
        </p>
      </div>
    </footer>
  )
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label}…</span>
    </div>
  )
}

export function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="notice notice-error" role="alert">
      <p>{message}</p>
      <button type="button" className="btn" onClick={onRetry}>
        Try again
      </button>
    </div>
  )
}
