# OPERA architecture

OPERA extends God's Eye View (GEV, upstream `bilawalsidhu/gods-eye-view`, MIT code,
v0.2.1 at the time of the M0 audit) with a photo-geolocation workflow. OPERA is
added as isolated modules; upstream files are left alone except for the small,
listed hook points in [DECISIONS.md](DECISIONS.md).

## 1. How upstream is structured (M0 audit)

| Area | Where | Notes |
|---|---|---|
| Entry | `index.html` -> `src/main.js` | `main.js` calls `createStandaloneApplication({googleApiKey, cesiumToken})` and `start()`. HTML chrome is assembled from `<!-- gev:template ... -->` placeholders by `build/application-html.js`. |
| Composition | `src/standalone/application.js` | Wires four constructors via `src/app/application.js`: `createScene`, `createControls`, `createData`, `createTools`. One standalone app per page. |
| **Cesium `Viewer` creation** | `src/standalone/scene.js` -> `createApplicationViewer` in `src/app/viewer.js` | Keyless default is Esri World Imagery; Cesium ion token and Google Photorealistic 3D Tiles are optional. |
| Debug/hook handle | `window.__godsEyeView` (`src/app/tools.js:145`) | Exposes `viewer`, `dataManager`, `requestRender`, ... while the app runs; deleted on destroy. **This is OPERA's integration point.** |
| Layers | `src/layers/<family>/`, catalog in `src/app/catalog.js` / `src/standalone/catalog.js` | Each layer has a source + controller + Cesium resources. |
| UI panels | `src/ui/` (rails: `leftPanelRail.js`, `rightPanelRail.js`, `panelRails.js`) | Rails measure/position each other. OPERA does not join the rails; it mounts its own fixed-position host so it cannot disturb rail layout. |
| Attribution | `src/data/dataCredits.js` -> `viewer.creditDisplay.addStaticCredit` | Expandable "Data attribution" lightbox, bottom-left. OPERA adds its own static credits through the same API. |
| Server | `server/standalone/vite.config.js` (re-exported by `vite.config.js`), `server/providers/*` | Vite dev server plus provider proxy routes (`/api/geocode`, `/api/route`, ...). Binds to localhost. Dev port 4173 (Vite picks the next free port). |
| OpenAI | `server/providers/openai.js`; env `OPENAI_API_KEY` | Used upstream for realtime voice. OPERA's backend reads the **same** variable (spec 5/M3). |
| Gates | `npm test` (node:test, `*.test.mjs` under `src/` and `server/`), `npm run check:boundaries`, `npm run format:check`, `npm run build` | Baseline recorded in PROGRESS.md (6534 tests, 0 fail). |

Gates that constrain OPERA code placed under `src/`:

* `scripts/check-import-directions.mjs` scans every runtime file in `src/`: no Node
  builtins, no `server/` imports, and non-entry modules must not import `src/standalone/`.
* `scripts/format.mjs` formats runtime roots listed in `scripts/format-runtime.json`.
* `scripts/run-unit-tests.mjs` discovers `*.test.mjs` only, so OPERA's Vitest files use
  `*.spec.js` and do not collide with the upstream runner.

## 2. Where OPERA hooks in

```
index.html
  └─ <script type="module" src="/src/opera/boot.js">   (one added line; the only upstream edit on the frontend)

src/opera/boot.js     waits for window.__godsEyeView.viewer, then mounts OPERA
  ├─ state/store.js              pub/sub store
  ├─ api/client.js               REST client; VITE_OPERA_MOCK=1 -> deterministic fixtures
  ├─ ui/*.js                     upload, clues, candidates, benchmark, developer panels
  ├─ globe/candidateOverlays.js  markers, uncertainty circles, fly-to, own removable entity collection
  └─ opera.css                   all styles namespaced `.opera-*`
```

Isolation rules: OPERA creates its own `Cesium.CustomDataSource` for overlays (removable in
one call), never touches upstream data sources, and registers its credits via
`viewer.creditDisplay.addStaticCredit`.

## 3. Backend (FastAPI, `backend/`)

```
Browser ── REST (JSON + multipart, X-OPERA-Key) ──► FastAPI
  routes/      health, analyze, models, datasets, evaluations
  services/    storage (TTL temp files), sanitize (re-encode, strip metadata),
               audit, ratelimit
  adapters/    base (Protocol), mock, vlm_clues (OpenAI), geoclip
  geo/         haversine, context_provider (Nominatim reverse geocoding, cached)
  eval/        runner, metrics, dedupe (hash + perceptual hash leakage checks)
  db           SQLAlchemy 2.x: SQLite (dev/tests), PostgreSQL+PostGIS (compose, untested here)
```

Data flow for `POST /api/v1/analyze`: validate (magic bytes, size, pixel limit) -> re-encode
without any EXIF/XMP/IPTC -> random-ID temp storage (TTL) -> adapters (VLM clues on the
sanitized, downscaled image only; GeoCLIP on the sanitized image) -> context provider labels
-> persist analysis + candidates -> response. Candidates and clue-model region guesses are
stored and returned separately; scores from different models are never merged.

## 4. Honesty labelling

Every result carries `model_kind` (`mock` | `real`), per-candidate `source_model`,
`uncalibrated: true` until M5 calibration exists, and `confidence_band`
(`low|medium|high`, or `abstain` at analysis level). The UI shows a `MOCK DATA` badge
whenever any mock output is on screen.
