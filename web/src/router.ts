import { useEffect, useState } from 'react'

export type Route = 'home' | 'upload' | 'scoreboard' | 'how' | 'notfound'

export const ROUTES: Array<{ route: Route; href: string; label: string; title: string }> = [
  { route: 'home', href: '#/', label: 'Tonight', title: 'CloudSea · Nandi Hills sunrise call' },
  { route: 'upload', href: '#/upload', label: 'Upload', title: 'Add your sunrise photo · CloudSea' },
  { route: 'scoreboard', href: '#/scoreboard', label: 'Scoreboard', title: 'Scoreboard · CloudSea' },
  { route: 'how', href: '#/how', label: 'How', title: 'How it works · CloudSea' },
]

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, '').split('?')[0].replace(/\/+$/, '')
  switch (path) {
    case '':
      return 'home'
    case '/upload':
      return 'upload'
    case '/scoreboard':
      return 'scoreboard'
    case '/how':
      return 'how'
    default:
      return 'notfound'
  }
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseHash(location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parseHash(location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}
