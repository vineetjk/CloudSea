# CloudSea build log

Times are IST. Newest entries at the bottom. Numbers here are measured or quoted from a cited source; anything estimated says so.

## 2026-10-10 12:18 — Start

- Challenge: DEV Hacktoberfest Open-Source AI Challenge, Week 1, theme "Touch Grass" (tag `#hf26challenge`). Submissions close 2026-10-11 23:59 PDT = **2026-10-12 12:29 IST**. That leaves about 48 wall-clock hours and two possible live sunrises: Sun 11 Oct and Mon 12 Oct.
- Machine: MacBook M2, 8 GB unified memory, macOS 15.0.1, Ollama 0.35.1, Docker 29.6.1, Python 3.14 (too new for some ML wheels; the project will pin 3.12).

## 2026-10-10 12:30 — Phase 0: docs verified

What we checked against current docs, and what changed in the plan because of it.

**Gemma 4 on Ollama**
- Gemma 4 needs Ollama ≥ 0.20.0; tool-calling fixes landed in 0.20.6. Local 0.35.1 is fine. ([v0.20.0](https://github.com/ollama/ollama/releases/tag/v0.20.0), [v0.20.6](https://github.com/ollama/ollama/releases/tag/v0.20.6))
- `gemma4:e2b` has two builds behind one tag: a 4.6 GB llama.cpp build (Q4_K_M) and a 7.5 GB MLX build. Since Ollama 0.40, Apple Silicon defaults to MLX. **Decision:** pin `gemma4:e2b-it-q4_K_M` everywhere, so the Mac and Render run identical weights. ([tags](https://ollama.com/library/gemma4/tags), [v0.40.0](https://github.com/ollama/ollama/releases/tag/v0.40.0))
- E2B supports vision, tools and thinking. Thinking is on by default, so we send `think: false` to save CPU. ([model page](https://ollama.com/library/gemma4:e2b), [v0.34.3](https://github.com/ollama/ollama/releases/tag/v0.34.3))
- `format` accepts a JSON schema and works with images. A third-party report says `format` combined with `tools` can block tool calls. **Decision:** the writer agent uses tools and returns plain text; the photo rater uses image + schema and no tools. ([structured outputs](https://docs.ollama.com/capabilities/structured-outputs))
- Licence: Apache 2.0. ([ai.google.dev/gemma/apache_2](https://ai.google.dev/gemma/apache_2))
- No published Ollama tokens/sec on x86 CPUs. Our Render benchmark will be original data.

**TabPFN (`tabpfn-client` 0.6.1)**
- Python 3.10–3.13. Auth via the `TABPFN_TOKEN` env var, no prompts. ([auth](https://docs.priorlabs.ai/api-reference/python/tabpfn-client/authentication.md))
- Hosted model limits (1M rows, 20k features) are far above our ~3k rows × <60 features. Fits are free; predictions cost tokens against 5M/day and 20M/month. ([models](https://docs.priorlabs.ai/models.md), [metering](https://docs.priorlabs.ai/api/metering.md))
- The terms require non-personal training data (ours is weather and labels). §7.4 allows Prior Labs to use uploaded data unless you opt out. ([terms](https://priorlabs.ai/terms))

**Render**
- Cron jobs can send requests to private services (they can't receive traffic). Same region and workspace required. ([private network](https://render.com/docs/private-network))
- Persistent disks attach to services, never to cron jobs. A disk pins a service to one instance with no zero-downtime deploys. ([disks](https://render.com/docs/disks)) **Decision (proposed):** photos go in Postgres `bytea`, not on a disk.
- Billing is per second. Cron jobs bill per minute of run time plus $1/month each (e.g. 4c-8g at $0.00405/min). Always-on 8 GB instances cost $135–175/month and 16 GB instances $200–225/month. Static sites are free. ([pricing](https://render.com/pricing), [cron jobs](https://render.com/docs/cronjobs))
- Plan names changed in August 2026 to IDs like `2c-8g`; old names still work. ([compute plans](https://render.com/docs/compute-plans))
- No GPU instances listed.

**Weather data**
- IEM's VOBL archive starts 2008-07-21, but rows before ~2011 come from ISD and have no sky or weather groups. Units: `vsby` in statute miles, `skyl` in feet. ([IEM help](https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?help))
- **Train/serve skew finding.** Open-Meteo's Historical Forecast API stitches together the first hours of each model run. A dawn value from it is close to an analysis, not something known at 8:30 PM the night before, so a model trained on it would look better in the backtest than it is live. Sources without that problem start in 2024:
  - The Single Runs API (`ecmwf_ifs` from 2024-03-14) gives the exact 06 UTC run available by 8:30 PM IST.
  - The Previous Runs API (from ~2024-02) has fewer variables. ([historical forecast](https://open-meteo.com/en/docs/historical-forecast-api), [single runs](https://open-meteo.com/en/docs/single-runs-api), [previous runs](https://open-meteo.com/en/docs/previous-runs-api))
  - Proposed: evening METAR features (2011+) plus the 06 UTC IFS run (2024+). To decide at the Phase 0 review.
- `relative_humidity_850hPa` is not in the reanalysis archive. It is in the Historical Forecast API (`best_match`, `gfs_seamless`) from 2021-03. That's acceptable for building the *label*, which is an after-the-fact judgement, but not as a forecast feature.
- Open-Meteo's `elevation` downscaling only adjusts temperature and pressure; cloud and fog fields are grid-cell values.
- Elevations:
  - VOBL is 915 m (3003 ft, [AIP India](https://aim-india.aai.aero/eaip/eaip-v2-09-2026/eAIP/IN-AD%202.1VOBL-en-GB.html)).
  - Nandi Hills summit is 1478 m ([Wikipedia](https://en.wikipedia.org/wiki/Nandi_Hills,_India); not checked against Survey of India).
  - The summit is ~563 m (1847 ft) above the airport, at roughly 850 hPa (GFS surface pressure 853 hPa at the summit point).
- Open-Meteo data is CC BY 4.0; attribution link "Weather data by Open-Meteo.com" required. ([licence](https://open-meteo.com/en/licence))

**Satellite (report only)**
- MOSDAC INSAT-3DS fog product: no files 06:30–09:30 IST on the sampled day, so it misses the sunrise window. Hard.
- Meteosat-9 IODC: 15-minute scans exist at dawn; account needed; native format. Medium.
- NASA GIBS Himawari visible tiles: cover Bangalore Aug–Oct 2026 but not earlier months; Bangalore is at the edge of the disk. Easy as a picture, not as a label.
- **Decision:** don't build. Possibly show a Himawari thumbnail on the live scoreboard as a stretch goal.

**Entire**
- Captures sessions through Claude Code hooks and git hooks; checkpoints are stored under `refs/entire/checkpoints/` and pushed with normal `git push`. A session that started before `entire enable` is not captured live; `entire session attach` can link it afterwards. ([docs](https://docs.entire.io/agents/setup))

## 2026-10-10 12:41 — Phase 0: VOBL METAR archive downloaded

- `make data-metar` (for now `python3 cloudsea/data/iem.py`): one request per station-year, 2 s pause. The first run died mid-2021 with `IncompleteRead` because IEM dropped a long chunked response. Writes go through a `.part` file and an atomic rename, so no partial file was left behind. Added a retry for dropped connections and resumed.
- 2008–2026: 297,037 reports in 19 yearly CSVs (53 MB, gitignored, reproducible).
- Coverage: 2008–2010 rows have no sky or weather groups (0–16%). 2011 is partial (157 days). 2012–2025 are full years, 92–98% of reports with sky groups. The dawn window (05:30–07:30 IST) holds a median of **5 reports** (half-hourly), and 336–366 days per year have ≥3 dawn reports.
- Dawn frequency by month (2011+, a day counts if any dawn report shows it), full table in `docs/phase0/metar_summary.md`:
  - Fog (FG): Oct 8%, Nov 21%, Dec 33%, Jan 34%, Feb 14%, ~0% Apr–Sep.
  - Mist (BR): 67–77% of dawns Oct–Feb.
  - BKN/OVC/VV below 1000 ft: Oct 31%, Nov 48%, Dec 55%, Jan 47%.
  - Any SCT-or-more layer below summit height (<1800 ft above the airport): 78–86% Oct–Jan, but **87–97% in Jun–Sep**.
- **Surprise:** "cloud below the summit" is true almost every monsoon morning. Then the summit is usually inside the cloud rather than above it. Airport data alone can't tell those apart, so the label needs a summit-level humidity term (~850 hPa).
- October is the start of the fog season, not the peak. Expect mostly SKIP calls during the live test.

## 2026-10-10 12:44 — Phase 0: Open-Meteo spike (one season, three points)

- Pulled the Historical Forecast API for Oct 2025–Feb 2026 at the airport, the plains south of Nandi and the summit, for `best_match` and `gfs_seamless`. All 11 requested variables came back 100% populated, including `relative_humidity_850hPa` and `_900hPa`, `cloud_cover_low`, `visibility` and `boundary_layer_height`.
- The summit request snaps to a grid cell at 1422 m (13.39 N, 77.66 E), matching the elevation reported earlier.
- Dawn (01 UTC = 06:30 IST) values over the season (151 days):
  - 850 hPa RH: min 9 / median 68 / max 100%.
  - 900 hPa RH: median 82–87%.
  - So the air at summit height varies a lot while the layer below is usually moist. That's the contrast the label needs.
- **GFS visibility is useless here:** min 13 km, flat-capped at 24 km, so it never forecasts fog. ECMWF (`best_match`) goes down to 60–80 m. Use ECMWF fields for anything about fog.
- Pressure-level values are nearly identical at the plains and summit points (same air column). The useful contrast is between levels, not between points.

## 2026-10-10 12:52 — Phase 0: environment, a secrets slip, Entire

- `uv` 0.13.0 with Python 3.12.15 (tabpfn-client supports 3.10–3.13). `make setup` creates the env and installs a pre-commit hook (`scripts/check-secrets.sh`) that blocks anything shaped like a TabPFN or Render key, and any `.env` file. Tested with a fake key; it blocked the commit.
- **Slip:** both API keys were first pasted into `.env.example`, the committed template, instead of `.env`. Caught before any commit. The values were moved to the gitignored `.env` without being printed. Because the editor had already shown them to the agent session, both keys must be rotated before any session transcript is published (pending as of 13:20).
- Entire CLI 0.11.4 enabled for Claude Code with telemetry off: 9 agent hooks in `.claude/settings.json`, git hooks for commit-msg, post-commit, post-rewrite, pre-push and prepare-commit-msg, and `.entire/settings.json`. Session pushing is off locally (`.entire/settings.local.json`) until the key rotation is confirmed.

## 2026-10-10 12:56 — Phase 0: TabPFN smoke test

- `make tabpfn-smoke`, with synthetic data only (300 train / 100 test rows × 30 features).
- The API's default model is **TabPFN v3.5** (8 estimators); 21 model versions are listed.
- Timing: fit 7.0 s, predict 2.3 s. A predict costs the 10,000-credit minimum against a 20M monthly limit (resets 1 Nov), so the backtest must batch its predictions.

## 2026-10-10 13:10 — Phase 0: Gemma 4 E2B on the Mac (M2, 8 GB)

- Model `gemma4:e2b-it-q4_K_M`: 4.6 GB download, 4.6B parameters including per-layer embeddings, Q4_K_M, needs Ollama ≥ 0.30.9. `ollama show` lists vision, audio, tools and thinking (thinking on by default).
- Test set: 14 Creative Commons photos of Nandi Hills from Wikimedia Commons (`make gemma-pull` fetches them and writes `ATTRIBUTION.md`).
  - I labelled them by eye: 3 cloud sea, 1 partial, 3 clear, 4 socked in, 3 too ambiguous to score.
  - These are reference labels for benchmarking, not ground truth.
- Speed: cold load 7–14 s, warm generation **22–28 tok/s**, prompt processing 400–500 tok/s, about **4 s per photo**.
- Memory: Ollama's resident memory was 1.0–2.5 GB, but macOS swapped 2.5–4.2 GB of other apps. 8 GB works with VS Code open, but only just.
- `ollama ps` reports the model as 0.24 GB. It doesn't count the memory-mapped per-layer embeddings, so don't size servers from it.

**First prompts failed (v1, kept in `bench_gemma_mac-m2-8gb_v1-naive-prompts.json`):**
- Writer agent: **0/5**. Told to "call every tool you need", it called only `get_leave_by` and wrote filler ("The forecast for tomorrow is available").
- Photo rater: valid JSON 14/14, but agreed with the reference labels **3/11**. It answered `cloud_sea` for nearly everything, including all four fog-at-the-summit photos, always with confidence 0.95.

**What fixed them (v2, the current code):**
- Writer: name all four tools in the system prompt. Now **5/5**, all four tools called in one round, 2.2–3.3 s, every number traceable to a tool result. The harness also re-asks for any tool the model skips; this was never needed in testing.
  - Still missing: it leaves out the probability and the "not a guarantee" line. The Phase 3 guardrail will check that required facts are present as well as that numbers are valid.
- Photo rater: ask evidence questions *before* the label (nearby objects hazy? ground visible far below? a layer below the horizon?).
  - **7–8/11** across runs (3/11 before). Fog at the summit is now recognised in 3–4 of 4 runs.
  - Remaining error: clear mornings with clouds in the sky get called `cloud_sea` or `partial`.
  - Dead ends:
    - Deriving the label in code from the answers did worse (4–5/11); the model says "layer below" for every photo.
    - Thinking mode did worse (3/11) and was 5× slower (~20 s per photo).
  - Confidence stays at 0.95 regardless, so it is not used.
  - Uploaders confirm or correct the label with one tap, and only confirmed labels count for grading.

## 2026-10-10 13:22 — Phase 0: can we get the forecast that exists at 8:30 PM?

- Open-Meteo Single Runs API, `ecmwf_ifs`, at the plains point (13.25 N, 77.68 E):
  - At 07:51 UTC today the **00 UTC run was available and the 06 UTC run was not**. Still to check: whether the 06 UTC run is out by 15:00 UTC (8:30 PM IST). If not, the nightly job uses the 00 UTC run.
  - Single runs return low cloud, visibility, boundary-layer height, dew point, temperature and wind, but **not** 850 hPa humidity.
- **A real example of why grading matters (10 Oct, this morning):**
  - Yesterday's 06 UTC ECMWF run forecast 06:30 IST at the plains point as **100% low cloud, visibility 220 m** (fog).
  - The airport reported **4000 m in mist (BR), FEW at 1000 ft, SCT at 1200 ft, 20/19 °C, wind 3 kt** from 05:30 to 08:00 IST.
  - Raw model fog was an overcall at the airport. The scattered layer sat below summit height (the summit is ~1850 ft above the airport), so Nandi may have had a partial sea. Nobody we know of reported from the top.
- Today's 00 UTC run forecasts 0% low cloud and 17.8 km visibility for Sun 11 Oct at 06:30 IST, so the first live morning is likely to be a SKIP.

## 2026-10-10 13:58 — Phase 1: the label

The user asked me to run all phases without stopping, so I chose the label myself. The reasoning is here and in `docs/phase1/label_report.md`; changing it is one line (`LABEL` in `cloudsea/label.py`).

- New data:
  - Summit-column fields at 06:30 IST from Open-Meteo's Historical Forecast API, 2021-03-23 to 2026-10-09: 48,648 hours, no gaps. 850 hPa humidity is used only for labels, never as a forecast feature.
  - One archived 00 UTC ECMWF IFS run per day since 2024-03-14, for Phase 2 features.
- Three definitions (`cloudsea/label.py`):
  - **A:** a low layer at the airport in ≥2 dawn reports, no rain.
  - **B:** A, plus 850 hPa humidity < 90%.
  - **C:** strict; fog or visibility < 1000 m in ≥2 reports, no deck at summit height, and 850 hPa humidity < 85%.
- **Chosen: B.** Base rates 2021–2026: Oct 22%, Nov 41%, Dec 53%, Jan 57%, Feb 21%.
  - A fires on 23% of July dawns, which is monsoon stratus with the summit inside it; B cuts that to 7%.
  - C keeps too few positives for a model to learn from.
- **Photo check (new, not in the original plan).**
  - Wikimedia Commons has 94 Nandi Hills photos whose EXIF capture time is 05:00–08:59 (2011+). I labelled 31 mornings by eye where the view below is visible (`docs/phase1/photo_reference_labels.csv`); 29 have enough airport reports to judge.
  - The airport rule said "sea" on 6 mornings and **5 were cloud seas**. It found **5 of 9** photographed cloud seas, and **never fired on the 6 socked-in or 3 partial mornings**.
  - Misses: two had one low-cloud report (one short of the 2-report rule), one had nothing at the airport (likely valley fog it can't see), and one photo was taken at 08:34.
  - Small sample, one labeller, camera clocks trusted. A sanity check, not proof.
- **Bug caught by the example days:** IEM stores visibility in statute miles, so "1500 m" comes back as 1497 m and passed "< 1500 m". Thresholds now have margins (`VIS_LOW_M = 1450`, `VIS_FOG_M = 950`), with a test that runs real reported values through the mile rounding. This lowered base rates by 2–9 points.
- `make label-report` regenerates everything; `tests/test_label.py` has 11 tests.

## 2026-10-10 14:18 — Phase 2: forecast model and backtest

- **Features (`cloudsea/features.py`)**, only what exists when the call goes out:
  - Airport reports up to **19:30 IST**. IEM ran 20–40 min behind real time today, so a 20:30 job can't count on the 20:00 report.
  - The **00 UTC ECMWF IFS run of the same day** (out by ~13:30 IST), for the night and the next dawn (+24..+26 h).
  - Rain reports in the last 24 h and 72 h, day of year, and the airport part of this morning's outcome.
- **Leakage check (`tests/test_leakage.py`)** scrambles every report after the cut-off, and the next dawn's summary, then asserts the features don't move. It caught a real bug: after I moved the cut-off from 20:00 to 19:30, the 24 h rain window still ended at 20:00. The window is now derived from the cut-off.
- **ECMWF backfill:** 937 of 941 daily runs (2024-03-14 to 2026-10-10) from the Single Runs API. The API sometimes takes 90 s per request; a 120 s timeout with 4 workers stalled, and 30 s with 8 workers finished.
- **Split:**
  - Train: target dates 2021-04-01 to 2025-09-30 (1639 rows, all months).
  - Test: the 2025-26 fog season (Oct–Feb, 151 nights, base rate 35%), untouched until the final scores.
  - Thresholds come from out-of-fold predictions on 2022-23, 2023-24 and 2024-25, each predicted by a model trained only on earlier rows.
- **Test season (`docs/results/backtest.json`):**

| | Brier | ROC-AUC | GO nights | GO precision |
|---|---|---|---|---|
| TabPFN, airport + ECMWF (live model) | 0.147 | 0.866 | 34 | 0.76 |
| Gradient-boosted tree, airport + ECMWF | 0.144 | 0.869 | 38 | 0.76 |
| TabPFN, airport only | 0.177 | 0.803 | 35 | 0.69 |
| Gradient-boosted tree, airport only | 0.201 | 0.724 | 23 | 0.70 |
| Monthly climatology | 0.204 | 0.704 | | |
| Persistence (like this morning) | 0.223 | 0.639 | | |
| Hand rule (spread ≤ 5 °C, wind ≤ 12 km/h, clear evening, no rain) | 0.250 | 0.526 | | |
| ECMWF raw dawn low-cloud fraction as probability | 0.398 | 0.545 | | |

- **Honest reading:**
  - With ECMWF features, TabPFN and the tree are **tied**. TabPFN's edge shows where data is thin. Out of fold it has the better Brier in every season (0.208 vs 0.260, 0.241 vs 0.273, 0.197 vs 0.218), with the biggest gap in 2022-23, trained on only 547 rows.
  - The earlier seasons are harder than the test season. Out-of-fold AUC was 0.72 (2022-23), 0.55 (2023-24) and 0.77 (2024-25), against 0.87 on 2025-26. Expect live skill somewhere in that range, not at the top of it. Per-season numbers: `docs/results/oof_by_season.csv`.
  - The textbook radiation-fog rule (spread ≤ 2 °C, wind ≤ 8 km/h) fired on 0% of training nights at 19:30 IST; Bangalore evenings are breezy and fog forms later. The loosened version was chosen on training rows only.
  - Raw ECMWF low cloud is a poor probability on its own (Brier 0.398, worse than climatology). TabPFN turns it into a calibrated call.
- **Thresholds (TabPFN, airport + ECMWF, from out-of-fold):** SKIP below 15%, GO at 60% or above, MAYBE in between. Targets: GO precision ≥ 60% and seas among SKIP nights ≤ 10%. I chose them myself because the user asked for all phases without stopping; they're one place in `backtest.json`.
- **Backtest headline (2025-26, weekend mornings only):** going every weekend = **43 trips, 17 cloud seas**; going only on GO = **12 trips, 10 cloud seas**; GO or MAYBE = 36 trips, 16 seas; SKIP missed 1 sea. Cloud sea here means the airport-based label, not a summit photo.
- **Cost:** each TabPFN prediction is billed at a 10,000-credit minimum. Predictions are now cached on disk (`data/interim/pred_cache`), so re-running the report costs nothing.
- **Live training data:** `make train-table` froze 2013 labelled rows (through 2026-10-08) into `data/model/train_table.parquet` (94 KB, committed). The grader appends each live day.

## 2026-10-10 14:30 — Phase 3: the app, deployed

- **How it was built.** Two parallel agents in their own git worktrees, both working to a written contract (`docs/API.md`):
  - The **frontend** agent built the React + Vite PWA: 56 KB gzipped main bundle, 24 tests, and checks in headless Chromium at 320 px.
  - The **API** agent built FastAPI, the Postgres layer, the photo pipeline and the share cards: 54 tests against real Postgres.
  - I wrote the ML side: Gemma writer and rater, sunrise and leave-by plan, nightly and grader jobs.
  - Each agent's report listed contract ambiguities. Two real bugs came out of the integration review:
    1. The How page said "going only on GO" but showed GO-or-MAYBE numbers.
    2. It called 43 weekend *mornings* "43 weekends".
- **Gemma writer guardrail, in practice:**
  - First live-like test: for a SKIP at 8%, Gemma wrote "GO, 0%" three times. The guardrail rejected all three and the template went out.
  - That exposed a guardrail bug: `json.dumps` escaped "°C" as `°`, which made "0" and "00" count as allowed numbers. Fixed and tested.
  - With a stricter prompt every draft passed, but one said "leave Electronics City by 03:40 from the parking area" (it had picked up "parking" from the carry list). Numerically valid, semantically wrong: a number guardrail can't catch that. The prompt now fixes a four-sentence order. Latest output: "SKIP: 8% chance of a cloud sea at Nandi Hills on Sun 11 Oct. Sunrise is at 06:07. Leave Electronics City by 03:40. Carry a warm layer, water, and a torch for the walk."
- **Leave-by:**
  - Drive times are OSRM free-flow on OpenStreetMap: Electronics City 79 km / 94 min, plus 8 more areas. The E-City time still needs a real-world check.
  - Each time adds a 20 min buffer and aims to arrive 30 min before sunrise.
  - The gate time shows as "not yet verified".
- **Sunrise:** astral with the observer 560 m above the plains gives Sun 11 Oct sunrise 06:07, first light 05:44.
- **Render:**
  - All services in Singapore, created through the API by `scripts/render_deploy.py`, which mirrors `render.yaml` (a Blueprint instance can't be created through the API).
  - `render.yaml` validates against Render's published JSON schema. That check caught `generation: off` being parsed as the boolean `false`.
  - Services created through the API rebuild on every push, so each now has a build filter (Gemma only on `infra/gemma/**`).
  - Live: web https://cloudsea-web.onrender.com, API https://cloudsea-api.onrender.com, private `cloudsea-gemma` (2c-8g, 10 GB disk), `cloudsea-nightly` (15:00 UTC = 20:30 IST), `cloudsea-grader` (02:45 UTC = 08:15 IST), `cloudsea-db` (Postgres 17, 0.1c-256mb).
  - About $152/month at these plans.
- **Render benchmark wrinkles:**
  - A plan change is applied in place without a new deploy, so the benchmark waited for a deploy that never came. Fixed by not waiting on deploys after a resize.
  - Wikimedia returned 403 to Render's IPs until the User-Agent carried a contact URL.
  - Final numbers, Gemma 4 E2B on CPU: 2c-8g 6.1 tok/s, a call in 11.8 s, a photo in 29.8 s; 4c-8g 6.4 tok/s for $40/month more.
