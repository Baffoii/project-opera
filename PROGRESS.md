# OPERA V1 progress

## Morning Summary
_(Work in progress - M0 done. This block is rewritten at the end of the session.)_

- Status: M0, M1 DONE; M2-M5 pending.
- Run upstream: `export PATH=$HOME/.opera-tools/node-v24.22.0-darwin-arm64/bin:$PATH && npm run dev`
- Mocked so far: the whole frontend runs on MOCK fixtures when `VITE_OPERA_MOCK=1` (badge shown in UI; `model_kind: "mock"`).
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
