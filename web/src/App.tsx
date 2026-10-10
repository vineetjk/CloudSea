import { Suspense, lazy, useEffect, useRef } from 'react'
import { Footer, Header, Loading } from './components/Chrome'
import { ROUTES, useRoute } from './router'
import Home from './pages/Home'
import Scoreboard from './pages/Scoreboard'
import How from './pages/How'

// The upload page (and exifr, which it loads) stays out of the first download.
const Upload = lazy(() => import('./pages/Upload'))

function NotFound() {
  return (
    <div className="page">
      <h1>Page not found</h1>
      <p>
        <a href="#/">Go to tonight's call</a>
      </p>
    </div>
  )
}

export default function App() {
  const route = useRoute()
  const first = useRef(true)
  const main = useRef<HTMLElement>(null)

  useEffect(() => {
    document.title = ROUTES.find((r) => r.route === route)?.title ?? 'CloudSea'
    if (first.current) {
      first.current = false
      return
    }
    // A new page: start at the top and move keyboard/screen reader focus to it.
    window.scrollTo(0, 0)
    main.current?.focus({ preventScroll: true })
  }, [route])

  return (
    <>
      <Header route={route} />
      <main id="main" ref={main} tabIndex={-1} className="container">
        {route === 'home' && <Home />}
        {route === 'upload' && (
          <Suspense fallback={<Loading label="Loading the upload page" />}>
            <Upload />
          </Suspense>
        )}
        {route === 'scoreboard' && <Scoreboard />}
        {route === 'how' && <How />}
        {route === 'notfound' && <NotFound />}
      </main>
      <Footer />
    </>
  )
}
