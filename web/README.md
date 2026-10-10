# CloudSea web

The CloudSea frontend: React 18, Vite and TypeScript, with no UI or CSS framework. The API contract is in [`../docs/API.md`](../docs/API.md).

## Run with demo data

```sh
npm install
VITE_MOCK=1 npm run dev
```

Open http://localhost:5173. Mock mode reads the fixtures in `src/mocks/` and shows a "Demo data" badge in the header. Choose a state with `?demo=`:

- `/?demo=skip` (default): a SKIP call, with a missed MAYBE graded the day before
- `/?demo=go`: a GO call
- `/?demo=none`: no call yet, and an empty scoreboard

On the upload page, mock mode adds a "Demo only" box that skips the time and place checks, so you can try the flow with any photo.

## Run against the API

`npm run dev` proxies `/api`, `/s/`, `/og/` and `/story/` to `http://localhost:8000`, so you can start the API there and open the app.

To use an API on another origin, set `VITE_API_BASE` at build time:

```sh
VITE_API_BASE=https://api.example.org npm run build
```

The API then needs CORS for this site's origin. Share links (`/s/{date}`) use `VITE_API_BASE`, or this site's own origin if it is empty.

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Dev server with the API proxy |
| `npm run build` | Type-check, then build to `dist/` (also writes `dist/sw.js`) |
| `npm run preview` | Serve `dist/`, with the same API proxy |
| `npm test` | Vitest unit tests for the photo rules (dawn window in IST, distance from the summit, resize loop) |
| `npm run icons` | Redraw `public/icon.svg` and the PNG icons |

## Notes

- The service worker is registered only in production builds. It caches the app shell and never caches `/api`, `/s`, `/og` or `/story`.
- The upload page and `exifr` load only when someone opens the upload page.
- Photo checks run on the device before upload: the photo must have been taken today between 05:00 and 08:30 IST, and within 3 km of the summit if it has GPS. Photos are resized to at most 1280 px and 200 KB. The canvas re-encode drops all EXIF.
- localStorage keys: `cloudsea.area` (leave-by area), `cloudsea.photos` (your uploads' ids and tokens), `cloudsea.going` (dates you tapped "I'm going").
