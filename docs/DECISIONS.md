# OPERA decisions log

One line of reasoning per decision. Newest at the bottom.

| # | Decision | Reasoning |
|---|---|---|
| D1 | Frontend lives in `src/opera/` (not a new top-level dir). | Upstream's build, boundary and format tooling all treat `src/` as the browser runtime; matches the spec's proposed layout. Import-direction gate verified compatible (no Node/server/standalone imports). |
| D2 | OPERA gets the Cesium viewer from `window.__godsEyeView.viewer`, not by importing `src/standalone/*`. | The boundary gate forbids non-entry modules importing standalone setup; the debug handle is the documented stable shape. |
| D3 | One added line in `index.html` (`<script type="module" src="/src/opera/boot.js">`) is the only upstream frontend edit. | Smallest possible hook; keeps `src/main.js` untouched. Everything else is additive. |
| D4 | Node 24.22.0 is installed as a user-local tarball at `~/.opera-tools/node-v24.22.0-darwin-arm64` (SHA-256 verified); system Node is 22.20 and fails upstream's `engines` + allocation-budget tests. | Spec/README require Node 24.x. Local tarball avoids touching global installs. Activate with `export PATH=$HOME/.opera-tools/node-v24.22.0-darwin-arm64/bin:$PATH`. |
| D5 | Python venv built from Python 3.13 (`/opt/homebrew/bin/python3.13`), not the system 3.14. | Spec asks for 3.12+; torch/GeoCLIP wheels for 3.14 are unlikely to exist yet. |
| D6 | Vitest config in a separate `vitest.config.js` with `*.spec.js` files. | Vite config is an upstream re-export (don't edit); Vitest prefers `vitest.config.js`. `*.spec.js` avoids upstream's `*.test.mjs` node:test discovery. |
| D7 | OPERA's own dev port: Vite picks the first free port from 4173 (4173 is held by another local process on this machine; left untouched). Backend defaults to `127.0.0.1:8000`. CORS origins are configurable via `OPERA_CORS_ORIGINS`. | Spec: "CORS restricted to the Vite dev origin". Not killing processes I do not own. |
| D8 | `X-OPERA-Key` used from the browser is exposed as `VITE_OPERA_API_KEY`. It is a shared secret for local/dev, not per-user auth. | Spec mandates the header; documented as a limitation in PRIVACY.md. Real multi-user auth is out of scope for V1. |
| D9 | SQLite from the start; PostGIS only through `docker-compose.yml` (not run: Docker not installed). | Operator instruction. Candidate geometry is stored as lat/lon columns on SQLite and `geography(Point)` only when `DATABASE_URL` is PostgreSQL; the Postgres path is **untested** and will be labelled so. |
