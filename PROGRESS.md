# OPERA V1 progress

## Morning Summary
_(Work in progress: M0-M4 done. This block is rewritten at the end of the session.)_

- Status: M0, M1, M2, M3, M4 DONE; M5 (benchmark, calibration, docs, compose) pending.
- Real now: `geoclip-v1` runs GeoCLIP locally on CPU through the full UI (a Lisbon photo with no EXIF returned Lisbon as rank 1, `model_kind: "real"`, about 10 s on first request incl. model load). Scores are raw, uncalibrated; thresholds are provisional.
- Mocked: with no `OPENAI_API_KEY`, clues are labelled `MOCK` (`clues_kind: "mock"`). The VLM adapter is **built, not yet verified against the live API** (tested with fake clients and a mocked HTTP transport only).
- Place names: candidates are labelled via OSM Nominatim (rounded coordinates only, cached, rate-limited, fails soft to coordinates). Set `OPERA_CONTEXT_USER_AGENT` to a real app name + contact before non-local use; never tested against the public service.
- Needs a human: licenses for GeoCLIP weights and the CLIP backbone (`needs_human_review` in `backend/registry/models.yaml`); PostGIS path and Google 3D tiles untested.
- Run backend: `cd backend && OPERA_API_KEY=<choose> .venv/bin/uvicorn --factory app.main:create_app --port 8000`; tests: `cd backend && .venv/bin/pytest`; frontend tests: `npx vitest run`.
- Run UI against it: `VITE_OPERA_API_KEY=<same> VITE_OPERA_API_URL=http://127.0.0.1:8000 npm run dev` (open the OPERA panel, Developer view shows the model selector and latency). `VITE_OPERA_MOCK=1` runs the UI with no backend.
- Go live with the VLM: add `OPENAI_API_KEY` to `.env` -> restart backend -> run `python scripts/smoke_vlm.py`.

---

## M0 - Audit upstream - DONE
**Changed files:** added `docs/ARCHITECTURE.md`, `docs/DATA_SOURCES_OPERA.md`, `docs/DECISIONS.md`, `PROGRESS.md`. No upstream files modified.
**Commands run:**
- Installed Node 24.22.0 locally (`~/.opera-tools`, SHA-256 verified) because system Node is 22.20 (upstream requires >=24.14).
- `npm ci`; `npm run check:boundaries`; `npm run format:check`; `npm test`.
- `npm run dev -- --host localhost --port 4173` (4173 was already held by another local process, so Vite used 4174); headless Chrome screenshot via the repo's puppeteer.
**Test evidence:** upstream `npm test`: `tests 6534 / pass 6533 / fail 0 / skipped 1` (main suite), plus two smaller suites 1/1 and 13/13 passing; `check:boundaries` passed (all exports checked); `format:check`: "Checked 1340 source files."
Globe check: headless Chrome loaded `http://localhost:4174/`, 8 canvases present, loading screen hidden, Austin 3D view + "Choose your first view" welcome dialog rendered. One console error: a 404 for an unnamed resource (upstream, pre-existing, not investigated).
**Mocked / stubbed:** nothing yet.
**Blockers:** none. (System Node 22 vs required 24 handled by D4.)
**Remaining work:** M1-M5.

## M1 - OPERA shell (frontend, mock mode) - DONE
**Changed files:** new `src/opera/{boot.js,app.js,config.js,validation.js,opera.css}`, `src/opera/api/{client,mockFixtures}.js`, `src/opera/state/store.js`, `src/opera/ui/{dom,uploadPanel,cluesPanel,candidatesPanel}.js`, `src/opera/globe/{candidateOverlays,overlayPlan}.js`, `tests/opera/*.spec.js`, `tests/opera/e2e/mock-ui.mjs`, `vitest.config.js`. Upstream edits (additive only): `index.html` (+1 script tag), `package.json`/`package-lock.json` (+vitest, +jsdom, +`opera:test` script), `.gitignore` (OPERA block).
**Commands run:** `npx vitest run`; `npm run format:check`; `npm run check:boundaries`; `npm test`; `npm run build`; `VITE_OPERA_MOCK=1 npm run dev -- --port 4180` + `node tests/opera/e2e/mock-ui.mjs http://localhost:4180 /tmp/opera-shots`.
**Test evidence:**
- Vitest: `Test Files 5 passed (5) / Tests 33 passed (33)` (validation, magic bytes, store, client mock + request shaping, panels, overlay plan).
- Upstream `npm test` unchanged: `tests 6534 / pass 6533 / fail 0 / skipped 1`. `format:check`: Checked 1353 source files. `check:boundaries` passed. `npm run build` succeeded.
- Browser E2E (headless Chrome, mock mode): 12/12 checks pass (mock badge, preview, attestation gating, 5 candidates, grouped clues, 5 globe markers, fly-to moves camera, active highlight, upstream data sources intact, collapse to launcher, overlays removed on destroy). Last 3 consecutive runs green.
**Mocked / stubbed:** All analysis output in this milestone is MOCK (labelled `MOCK DATA` in the header, clues and candidates panels, `model_kind: "mock"`, labels prefixed `MOCK:`). Real-mode client paths (multipart analyze, get, delete, health, models, datasets) are written and unit-tested against a fake `fetch` but there is no backend yet. Filename containing "abstain" triggers the mock abstained state.
**Blockers:** none.
**Known issues / honesty notes:**
- Two early E2E runs failed (first: test clicked while upstream's loading overlay was still up - fixed by waiting for `#loading-screen.hidden`; second: a `.opera-candidate` timeout that I did not conclusively root-cause. Vite's log shows dev-server page reloads triggered by file writes while the test was running, which is the suspected cause. Subsequent 3 runs with no source edits all passed. I added a diagnostic dump to the script so a recurrence is explained.)
- Candidate uncertainty circles use `ClassificationType.BOTH` (draped on terrain/3D tiles, fill only, no outline). Visual check was done on the Esri/keyless view only; Google 3D tiles were not tested (no key).
- The OPERA panel is a fixed-position panel at the right (top 84px); I only looked at it in screenshots at 1440x900 and did not exhaustively check overlap with upstream right-rail panels at other sizes.
**Remaining work:** Dev panel/model selector (M3), benchmark UI (M5), OSM attribution credit once Nominatim labels exist (M4).

## M2 - Backend foundation - DONE
**Changed files:** new `backend/` (`pyproject.toml`; `app/{config,schemas,db,context,registry,main}.py`; `app/services/{sanitize,storage,ratelimit,audit,pipeline,sweeper}.py`; `app/adapters/{base,mock,registry}.py`; `app/geo/haversine.py`; `app/routes/{deps,health,analyze,registry}.py`; `registry/{models,datasets}.yaml`; `tests/*`). Edited: `.env.example` (OPERA block appended), `.gitignore` (+`*.egg-info/`), `docs/DECISIONS.md` (D10-D17), frontend `ui/cluesPanel.js` + `ui/candidatesPanel.js` (MOCK badge on clues now follows `clues_kind`; shows backend `notices`; distinct `failed` state) and `tests/opera/panels.spec.js` (+2 tests).
**Commands run:** `backend/.venv/bin/pytest`; mutation check of the EXIF test; live `uvicorn --factory` on :8011 with curl (health, authenticated analyze, unauthenticated 401), then stopped; `npx vitest run`; browser E2E on :4180 (stopped after); upstream `npm test`, `npm run build`, `format:check`, `check:boundaries`.
**Test evidence:**
- Backend pytest: `41 passed in 0.73s`. Covers health, auth (missing/wrong/non-ASCII key, fail-closed with no key), rate limit (429 + Retry-After, health exempt), CORS origin restriction, bad type / spoofed extension / GIF / garbage body / oversize (body and Content-Length) / pixel bomb, rights attestation, unknown/unavailable model, EXIF+GPS+XMP stripping (source fixture asserted to contain GPS first; output checked via parsed tags and raw bytes; PNG text/eXIf chunks), orientation applied before stripping, analyze->get->delete lifecycle (file and rows gone, 204 then 404), TTL sweeper, cascade delete, audit log contents (no ids/filenames/IP), band thresholds, abstention, adapter failure, clue adapter output kept separate from candidates, cost from tokens, haversine, token bucket, storage traversal safety.
- Mutation check: making the sanitizer pass the original EXIF through made 3 tests fail; restored and re-ran: 41 passed. One real bug found and fixed by the tests (latency JSON not persisted because the same dict was mutated).
- Vitest: `Test Files 5 passed (5) / Tests 35 passed (35)`. Browser E2E (mock mode): 12/12 PASS, no console errors. Upstream `npm test` unchanged: `tests 6534 / pass 6533 / fail 0 / skipped 1`; `format:check` Checked 1353 source files; `check:boundaries` passed; `npm run build` succeeded.
**Mocked / stubbed:** only the `mock` geo adapter is functional (labelled `model_kind: "mock"`, labels `MOCK: ...`). `geoclip-v1` is an `unavailable` placeholder and `analyze` with it returns 503; `vlm-clues` is an `unavailable` placeholder (reason "no key"). Candidate `uncertainty_km` is a per-band heuristic, not a measured error. Every candidate is `uncalibrated: true`.
**Blockers:** none.
**Known issues / honesty notes:**
- PostgreSQL/PostGIS path (`ensure_postgis`, docker-compose) is untested: Docker is not installed. SQLite only.
- Rate limiter is in-memory, single-process. The sync `POST /analyze` runs inference inline; no job queue (fine for V1 single-user).
- The frontend defaults to `model=geoclip-v1`, so against this backend a real-mode analyze returns a visible 503 until M3 adds GeoCLIP and the model selector. I did not test the real-mode frontend against the live backend in a browser (only unit tests against a fake fetch, and curl against the backend).
- No Alembic migrations: `create_all` only (D-log). Audit log is never pruned.
**Remaining work:** M3 (VLM adapter, GeoCLIP, dev panel/model selector), M4 (Nominatim context), M5 (benchmark, docs, compose, final summary).

## M3 - Real inference - DONE (VLM adapter not verified live)
**Changed files:** new `backend/app/adapters/{vlm_clues,geoclip}.py`, `backend/scripts/smoke_vlm.py`, `scripts/smoke_vlm.py` (repo-root launcher), `backend/tests/{test_vlm_clues,test_geoclip_adapter,test_pipeline_clues}.py`, `src/opera/ui/devPanel.js`, `tests/opera/e2e/real-ui.mjs`. Edited: `backend/app/{config,schemas,services/pipeline}.py`, `backend/app/adapters/{base,mock,registry}.py`, `backend/registry/models.yaml`, `backend/pyproject.toml` (geoclip extra pinned, respx dropped), `backend/tests/{conftest,test_lifecycle}.py`, `src/opera/{app.js,opera.css,state/store.js}`, `tests/opera/panels.spec.js`, `.env.example`, `docs/DECISIONS.md` (D18-D27). **One upstream edit:** `build/vite.js` CSP `connect-src` (D26).
**Commands run:** `pip install torch geoclip transformers` into `backend/.venv` (weights in the wheel; CLIP backbone ~1.6 GB downloaded to git-ignored `backend/.model_cache`); `backend/.venv/bin/pytest`; `npx vitest run`; `npm test`; `npm run check:boundaries`; `npm run format:check`; live `uvicorn` on :8000 + Vite on :4180 with logs in `/tmp/opera-e2e`, `node tests/opera/e2e/real-ui.mjs` and the mock E2E, then all servers stopped.
**Test evidence:**
- Backend pytest: `68 passed` (was 41). New: VLM adapter via fake client (success + caps, request shape with `store=False`/structured output/downscaled data URL, model abstain, refusal is not an abstain, unparsable, incomplete, timeout, 429-style error without leaking detail, unavailable states), the real OpenAI SDK driven through `httpx.MockTransport` (checks URL, model, strict json_schema, data-URL image, no filename, auth header), strict-schema keyword walk, GeoCLIP NMS and fake-model predict, and a **real GeoCLIP inference test** on a synthetic image (ran, not skipped), pipeline cases (mock-clue fallback, real clue cost/versions, abstain, refusal notice, clue failure continues, exception detail not leaked, stage/notes merge, latency total).
- Vitest: `Test Files 5 passed (5) / Tests 40 passed (40)` (+5 developer panel tests).
- Real-mode browser E2E (`real-ui.mjs`, headless Chrome, real backend, EXIF-free Commons photo of Elevador da Lavra, Lisbon): 13/13 PASS, no console errors. Candidates (rank, lat, lon, raw score, band): `1 38.71 -9.13 0.0129 low`, `2 41.15 -8.61 0.0022`, `3 40.21 -8.43 0.0011`, `4 39.91 -9.58 0.0003`, `5 39.40 -9.13 0.0002`; `model_kind: "real"`, `geo_adapter: geoclip-v1@geoclip-1.2.3`. Latency (first request, includes one-off model load): sanitize 282 ms, model_load 5107 ms, model_infer 4830 ms, geolocate 9938 ms, browser round trip about 10.7 s.
- Mock-mode E2E: 12/12 PASS. Upstream `npm test`: `tests 6534 / pass 6533 / fail 0 / skipped 1` (+1/1, +13/13); `check:boundaries` passed; `format:check` passed.
**Mocked / stubbed:** `mock-clues` shown whenever the real VLM is unavailable (the case in this build); labelled `MOCK` in the UI and notices. `mock` geo adapter remains selectable.
**Blockers:** none. (OSV-5M fallback was not needed.)
**Known issues / honesty notes:**
- **VLM clue adapter: built, not yet verified against live API.** The model name, prices, and strict-schema acceptance come from docs and local checks only; the owner's `scripts/smoke_vlm.py` run is the first live test.
- A real bug was found only by running real mode in a browser: upstream CSP blocked `http://127.0.0.1:8000` (D26). Another was `latency_ms.total` double counting (D27, test added).
- My first mocked-HTTP attempt (respx) did not intercept the SDK and sent one request with a fake key to api.openai.com (rejected 401; the payload was a synthetic JPEG). I replaced it with an injected `httpx.MockTransport` so tests cannot reach the network, and removed respx.
- Real scores are tiny raw gallery masses (0.0002-0.056). Bands and the abstention threshold are provisional (D25) and the single-photo run above is an anecdote, not an accuracy claim. M5 will measure.
- Candidates show coordinates only until M4. First request is slow (model load); the model stays loaded afterwards.
- Licenses: GeoCLIP code is MIT (LICENSE read from the wheel). Weights and the OpenAI CLIP backbone licenses were not read: `needs_human_review`.
- The OPERA panel in the 1440x900 screenshot sits under upstream's first-run "Choose your first view" dialog on a fresh profile; not changed.
**Remaining work:** M4 (Nominatim context + OSM attribution, candidate region labels), M5 (benchmark mode, calibration, docker-compose (untested), README/API/PRIVACY docs, final Morning Summary).

## M4 - Geographic context - DONE (optional boundary overlay and Overture not built)
**Changed files:** new `backend/app/geo/context_provider.py`, `backend/tests/{test_context_provider,test_pipeline_context}.py`, `tests/opera/e2e/nominatim_stub.py`. Edited: `backend/app/{config,context,db,main,schemas}.py`, `backend/app/routes/health.py`, `backend/app/services/pipeline.py`, `src/opera/{app.js,globe/candidateOverlays.js,ui/candidatesPanel.js}`, `tests/opera/{panels.spec.js,e2e/real-ui.mjs}`, `.env.example`, `docs/{DECISIONS,DATA_SOURCES_OPERA}.md` (D28-D34).
**Commands run:** `backend/.venv/bin/pytest`; `npx vitest run`; `npm test`; `npm run check:boundaries`; `npm run format:check`; mock E2E (`VITE_OPERA_MOCK=1`, :4180); real E2E with local stub: `python tests/opera/e2e/nominatim_stub.py 8099`, backend with `OPERA_CONTEXT_BASE_URL=http://127.0.0.1:8099`, `STUB_URL=http://127.0.0.1:8099 node tests/opera/e2e/real-ui.mjs ...`. All servers I started were stopped afterwards; logs in `/tmp/opera-e2e`.
**Test evidence:**
- Backend pytest: `90 passed` (was 68). New provider tests (httpx.MockTransport + fake clock): parse + policy headers + coordinate rounding, cache hit without a second request, stale fallback after TTL, ocean `no_result`, 5xx retry with backoff, timeouts exhaust retries, 429 not retried + cooldown + recovery, >=1.1 s spacing, deadline respected, invalid JSON/unexpected status without detail leak, repeated-failure cooldown, disabled provider. Pipeline tests: names + context + attribution persisted and returned by GET, **total provider failure still returns 3 candidates with a notice and no attribution**, partial failure, provider bug exposes only the exception type, mock candidates never geocoded, no provider configured, abstained analyses not geocoded, health lists the provider, old SQLite gains the column.
- Vitest: `Test Files 5 passed (5) / Tests 42 passed (42)` (+2: failed lookup vs open water with coordinates still shown; stale note + attribution line).
- Real-mode browser E2E (real GeoCLIP, local Nominatim stub): all checks PASS, no console errors. First analysis with the provider returning HTTP 500: 5 candidates still render with "Place name unavailable" + coordinates, notice shown, no OSM attribution. Second analysis with the stub answering: labels "Stubville, Test Region, Testland", `context.status: "ok"`, attribution in the panel and a static Cesium credit on screen (bounding box > 0). Context stage took ~2.2 s for the failing case.
- Mock E2E: 12/12 PASS. `npm test`: 13/13 (smaller suite) green; `check:boundaries` passed; `format:check`: Checked 1354 source files.
**Mocked / stubbed:** Place names in E2E come from a local stub, not OSM. Mock-model candidates keep their `MOCK:` labels and are not enriched.
**Blockers:** none.
**Known issues / honesty notes:**
- **No live request was made to the public Nominatim** (D30): the default User-Agent is a placeholder; the owner must set `OPERA_CONTEXT_USER_AGENT` with real contact details first. Real response parsing is tested against hand-written JSONv2 samples only, so field names for unusual regions (e.g. `municipality`-only results) are unverified.
- The cache is in memory (lost on restart, per process). The 1.1 s spacing means five uncached candidates cost about 5.5 s; cached lookups are instant. A self-hosted Nominatim via `OPERA_CONTEXT_BASE_URL` would be the answer for volume.
- Not built: country/admin boundary overlay, Overture provider (both optional; D34).
- ODbL share-alike obligations for stored results were not analysed; recorded as `needs_human_review`.
**Remaining work:** M5.
