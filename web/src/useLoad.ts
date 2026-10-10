import { useCallback, useEffect, useState } from 'react'
import { ApiError } from './api'

export type Load<T> = { status: 'loading' } | { status: 'ok'; data: T } | { status: 'error'; error: string }

// Last good response per loader, so going back to a page shows it at once
// while a fresh copy loads.
const cache = new Map<unknown, unknown>()

export function useLoad<T>(fn: () => Promise<T>): [Load<T>, () => void] {
  const [state, setState] = useState<Load<T>>(() =>
    cache.has(fn) ? { status: 'ok', data: cache.get(fn) as T } : { status: 'loading' },
  )
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    fn().then(
      (data) => {
        cache.set(fn, data)
        if (live) setState({ status: 'ok', data })
      },
      (err: unknown) => {
        if (!live) return
        const error = err instanceof ApiError ? err.message : 'Something went wrong. Please try again.'
        // Keep showing a cached copy rather than replacing it with an error.
        setState((s) => (s.status === 'ok' ? s : { status: 'error', error }))
      },
    )
    return () => {
      live = false
    }
  }, [fn, attempt])

  const reload = useCallback(() => {
    setState({ status: 'loading' })
    setAttempt((a) => a + 1)
  }, [])

  return [state, reload]
}
