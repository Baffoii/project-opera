# OPERA V1 progress

## Morning Summary
_(Work in progress - M0 done. This block is rewritten at the end of the session.)_

- Status: M0 DONE; M1-M5 pending.
- Run upstream: `export PATH=$HOME/.opera-tools/node-v24.22.0-darwin-arm64/bin:$PATH && npm run dev`
- Mocked so far: nothing built yet.
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
