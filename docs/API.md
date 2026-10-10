# CloudSea API contract

The `api` service (FastAPI) serves JSON under `/api`, plus share pages and images. All times are IST (`Asia/Kolkata`), with dates as `YYYY-MM-DD`. "Call date" means the date of the sunrise being forecast.

The frontend reads the base URL from `VITE_API_BASE` (default `""`, same origin in dev via the Vite proxy).

## GET /api/today

Tonight's call, or the most recent one.

```json
{
  "status": "ok",
  "call": {
    "date": "2026-10-11",
    "issued_at": "2026-10-10T20:30:12+05:30",
    "verdict": "SKIP",
    "probability": 0.08,
    "sunrise": "06:09",
    "first_light": "05:46",
    "text": "SKIP for Sunday. 8% chance of a cloud sea at Nandi. Sunrise 06:09. If you go anyway, leave Electronics City by 03:39. Carry a light jacket; it's 17°C at the top. A forecast, not a guarantee.",
    "text_kn": null,
    "text_hi": null,
    "carry": ["Light jacket (summit about 17°C)", "Water", "Torch for the walk from parking"],
    "conditions": { "summit_temp_c": 17, "wind_kmh": 9, "rain_last_24h": false },
    "leave_by": [
      { "area": "electronics-city", "label": "Electronics City", "drive_minutes": 100, "buffer_minutes": 20, "leave_by": "03:39" }
    ],
    "gate": { "opens": "06:00", "verified": false, "note": "Gate time not yet verified. Check before you go." },
    "model": { "forecaster": "TabPFN v3.5 (Prior Labs)", "writer": "Gemma 4 E2B", "trained_through": "2025-09-30" },
    "going_count": 4
  },
  "last_graded": {
    "date": "2026-10-10", "verdict": "MAYBE", "probability": 0.41,
    "airport_outcome": "no_sea", "photo_outcome": null, "correct": false
  }
}
```

- `status` is `"no_call_yet"` with `call: null` before the first nightly run.
- `verdict` is one of `GO`, `MAYBE`, `SKIP`.
- `probability` is in 0–1; show it as a whole percent.
- `leave_by` lists every supported area. The frontend shows the user's chosen area, stored in `localStorage` under `cloudsea.area`, default `electronics-city`.
- `text` is Gemma's call (≤ 45 words). Every number in it was checked against the tool results; if the check failed, `text` is a template fallback. The frontend never needs to know which.
- `airport_outcome` is one of `cloud_sea`, `no_sea`, `null` (not graded yet).
- `photo_outcome` is `null` or a majority label from confirmed photos: `cloud_sea | partial | clear_no_sea | socked_in`.
- `correct` is `true`, `false` or `null`. GO and MAYBE count as correct on a cloud sea; SKIP counts as correct on no sea.

## GET /api/scoreboard

```json
{
  "summary": { "graded": 2, "correct": 2, "go_calls": 0, "go_hits": 0, "brier": 0.09, "since": "2026-10-11" },
  "days": [
    {
      "date": "2026-10-11", "verdict": "SKIP", "probability": 0.08,
      "airport_outcome": "no_sea", "photo_outcome": "clear_no_sea", "photos": 3, "correct": true,
      "evidence": "VOBL 05:30-07:30: vis 6000 m, FEW020, no fog"
    }
  ],
  "agreement": { "days_with_both": 1, "airport_and_photos_agree": 1 }
}
```

`days` are newest first. The live scoreboard only includes calls that were issued live, never backtest days. The backtest is a static result shown on the "How it works" page from `GET /api/backtest`.

## GET /api/backtest

```json
{
  "season": "2025-26",
  "headline": { "weekends": 22, "every_weekend_seas": 5, "cloudsea_trips": 6, "cloudsea_seas": 4 },
  "metrics": [ { "model": "TabPFN", "brier": 0.11, "roc_auc": 0.84, "go_precision": 0.62 } ],
  "calibration": [ { "bin": "0-10%", "predicted": 0.05, "observed": 0.04, "n": 80 } ]
}
```

The numbers above only show the shape. Real values come from `docs/results/backtest.json`.

## POST /api/going

Anonymous "I'm going" tap. Body `{ "date": "2026-10-11" }`. Response `{ "count": 5 }`. Limited to one tap per IP per date, enforced server-side on a salted IP hash. Repeat taps return the current count with HTTP 200.

## POST /api/photos  (multipart/form-data)

The client resizes and checks the photo first:

1. Read EXIF with `exifr` before resizing: `DateTimeOriginal`, plus GPS if present.
2. Reject on the client, with a friendly message, if the photo wasn't taken today between 05:00 and 08:30 IST. If GPS is present, also reject if it's more than 3 km from the summit (13.3702, 77.6835).
3. Resize with a canvas to at most 1280 px on the long edge, as a JPEG of ≤ 200 KB. Lower the quality step by step if needed. Canvas output carries no EXIF.

Fields:
- `photo`: the resized JPEG
- `taken_at`: ISO timestamp with offset, from EXIF
- `gps_present`: `"true"` or `"false"`
- `distance_km`: optional, sent when GPS is present
- `public`: `"true"` or `"false"`, default false

The server checks the size (≤ 250 KB), checks `taken_at` against the dawn window again, re-encodes the image with Pillow (so no EXIF survives either way), and rate-limits to 5 uploads per IP per day.

Response `201`:
```json
{ "id": "p_7f3a…", "token": "t_…", "status": "queued" }
```
The client keeps `{id, token}` in `localStorage` (`cloudsea.photos`).

Errors are `400` / `413` / `429`, with `{ "error": "human readable message" }`.

## GET /api/photos/{id}?token=…

```json
{
  "id": "p_7f3a…", "date": "2026-10-11", "status": "rated",
  "rating": { "label": "cloud_sea", "confidence": 0.95, "evidence": "A white layer fills the valleys below the viewpoint." },
  "confirmed_label": null, "public": false
}
```
`status` is `queued` or `rated`. Gemma rates asynchronously, usually within a few minutes. Poll every 15 s while queued.

## POST /api/photos/{id}/confirm

Body `{ "token": "t_…", "label": "cloud_sea", "public": true }`, where `label` is one of `cloud_sea | partial | clear_no_sea | socked_in`. This is the one-tap "yes, that's right" or correction. Response: the photo object as above.

## GET /api/gallery

Public photos with a confirmed label, newest first: `[{ "id", "date", "label", "image_url" }]`.

## GET /api/photos/{id}/image

The JPEG itself. Served only if the photo is public, or if the request has `?token=` matching the owner.

## Share

- `GET /s/{date}`: a minimal HTML page with Open Graph tags (`og:title` such as "SKIP · 8% cloud sea · Sun 11 Oct", `og:image` = `/og/{date}.png`). It redirects people (not crawlers) to the web app.
- `GET /og/{date}.png`: a 1200×630 card.
- `GET /story/{date}.png`: a 1080×1920 card for Instagram or WhatsApp stories.
- WhatsApp link from the frontend: `https://wa.me/?text=` + URL-encoded `"{verdict} · {pct}% cloud sea at Nandi · {Day DD Mon}. {API_BASE}/s/{date}"`.
