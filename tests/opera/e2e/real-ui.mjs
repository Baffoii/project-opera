// Browser acceptance test of OPERA against a REAL backend (GeoCLIP). Usage:
//   OPERA_API_KEY=k OPERA_CORS_ORIGINS=http://localhost:4180 backend/.venv/bin/uvicorn --factory app.main:create_app --port 8000
//   VITE_OPERA_API_KEY=k VITE_OPERA_API_URL=http://127.0.0.1:8000 npm run dev -- --host localhost --port 4180
//   node tests/opera/e2e/real-ui.mjs http://localhost:4180 /path/to/photo.jpg /tmp/shots
import { mkdirSync } from 'node:fs';
import puppeteer from 'puppeteer';

const [url = 'http://localhost:4180', photo, outDir = '/tmp/opera-real-shots'] =
  process.argv.slice(2);
if (!photo) throw new Error('Pass the path of a photo as the second argument.');
mkdirSync(outDir, { recursive: true });

const browser = await puppeteer.launch({
  headless: true,
  args: [
    '--use-gl=angle',
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
    '--no-sandbox',
  ],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900 });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on(
  'console',
  (m) => m.type() === 'error' && errors.push(m.text().slice(0, 200)),
);
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction('window.__opera && window.__godsEyeView?.viewer', {
  timeout: 90000,
});
await page.waitForFunction(
  "document.querySelector('#loading-screen')?.classList.contains('hidden')",
  { timeout: 90000 },
);
const results = {};
const check = (name, ok) => {
  results[name] = !!ok;
  console.log(ok ? 'PASS' : 'FAIL', name);
};

check(
  'no frontend MOCK DATA badge in the header',
  (await page.$('.opera-header .opera-badge-mock')) === null,
);
await page.click('.opera-dev-toggle');
await page.waitForFunction(
  "document.querySelectorAll('#opera-model option').length >= 2",
  { timeout: 15000 },
);
const options = await page.$$eval('#opera-model option', (os) =>
  os.map((o) => ({
    value: o.value,
    disabled: o.disabled,
    text: o.textContent,
  })),
);
console.log('model options:', JSON.stringify(options));
check(
  'geoclip-v1 is offered and usable',
  options.some((o) => o.value === 'geoclip-v1' && !o.disabled),
);
check(
  'real model preselected',
  (await page.$eval('#opera-model', (s) => s.value)) === 'geoclip-v1',
);

await (await page.$('.opera-root input[type=file]')).uploadFile(photo);
await page.waitForSelector('.opera-preview img');
await page.click('#opera-rights');
const started = Date.now();
await page.click('.opera-btn-primary');
await page.waitForSelector('.opera-candidate', { timeout: 180000 });
console.log('wall clock for analysis (ms):', Date.now() - started);

const state = await page.evaluate(() => {
  const { analysis, roundTripMs, error } = window.__opera.store.get();
  return { analysis, roundTripMs, error };
});
const a = state.analysis;
console.log(
  'analysis summary:',
  JSON.stringify({
    status: a.status,
    model_kind: a.model_kind,
    clues_kind: a.clues_kind,
    versions: a.versions,
    latency_ms: a.latency_ms,
    candidates: a.candidates.map((c) => [
      c.rank,
      +c.lat.toFixed(2),
      +c.lon.toFixed(2),
      +c.score.toFixed(4),
      c.confidence_band,
    ]),
    notices: a.notices,
  }),
);
check('no UI error', !state.error);
check('analysis is from the REAL model', a.model_kind === 'real');
check(
  'adapter is geoclip',
  String(a.versions?.geo_adapter).startsWith('geoclip-v1@'),
);
check(
  '5 candidates in the UI',
  (await page.$$('.opera-candidate')).length === 5,
);
check(
  'candidates section carries no MOCK badge',
  await page.$eval(
    '[aria-label="Candidate locations"]',
    (e) => !e.querySelector('.opera-badge-mock'),
  ),
);
check(
  'candidates flagged uncalibrated',
  a.candidates.every((c) => c.uncalibrated === true),
);
check(
  'latency recorded (backend stages + browser round trip)',
  a.latency_ms.geolocate > 0 && state.roundTripMs > 0,
);
check(
  'latency shown in developer view',
  await page.$eval(
    '.opera-dev',
    (e) =>
      /Latency: geolocate/.test(e.textContent) &&
      /round trip/.test(e.textContent),
  ),
);
check(
  'globe shows 5 markers',
  (await page.evaluate(
    () =>
      window.__godsEyeView.viewer.dataSources.getByName('opera-candidates')[0]
        .entities.values.length,
  )) === 5,
);
await new Promise((r) => setTimeout(r, 3500));
await page.screenshot({ path: `${outDir}/real-01-analyzed.png` });

// Toggle VLM clues off and re-run: clues must disappear and the notice must not mention MOCK clues.
await page.click('#opera-vlm');
await page.click('.opera-btn-primary');
await page.waitForFunction(
  "window.__opera.store.get().status === 'idle' && window.__opera.store.get().analysis?.clues_kind === 'none'",
  { timeout: 180000 },
);
check('VLM toggle off yields no clues', true);
await page.screenshot({ path: `${outDir}/real-02-no-vlm.png` });
console.log(
  'console/page errors:',
  errors.filter((e) => !/404/.test(e)),
);
await browser.close();
process.exit(Object.values(results).every(Boolean) ? 0 : 1);
