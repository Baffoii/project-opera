// Browser test of OPERA's benchmark game. Works against the frontend mock (VITE_OPERA_MOCK=1) or a real
// backend that has the committed synthetic dataset (opera-synthetic-v1). Usage:
//   node tests/opera/e2e/benchmark-ui.mjs http://localhost:4180 /tmp/shots [mock|real]
import { mkdirSync } from 'node:fs';
import puppeteer from 'puppeteer';

const [
  url = 'http://localhost:4180',
  outDir = '/tmp/opera-bench-shots',
  kind = 'mock',
] = process.argv.slice(2);
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
const entityCount = () =>
  page.evaluate(
    () =>
      window.__godsEyeView.viewer.dataSources.getByName('opera-benchmark')[0]
        ?.entities.values.length ?? -1,
  );
const clickButton = async (text) => {
  await page.waitForFunction(
    (t) =>
      [...document.querySelectorAll('.opera-bench button')].some(
        (b) => b.textContent === t && !b.disabled,
      ),
    { timeout: 60000 },
    text,
  );
  await page.evaluate((t) => {
    [...document.querySelectorAll('.opera-bench button')]
      .find((b) => b.textContent === t && !b.disabled)
      .click();
  }, text);
};
const phase = () =>
  page.evaluate(() => window.__opera.store.get().benchmark.phase);
const waitPhase = (p) =>
  page.waitForFunction(
    (x) => window.__opera.store.get().benchmark.phase === x,
    { timeout: 120000 },
    p,
  );

await page.click('.opera-tab[data-mode="benchmark"]');
check(
  'benchmark panel is shown and the analyze panels are hidden',
  await page.evaluate(
    () =>
      !document.querySelector('.opera-bench').hidden &&
      document.querySelector('.opera-mode-analyze').hidden,
  ),
);
if (kind === 'mock')
  check(
    'mock mode labels the benchmark panel MOCK DATA',
    (await page.$('.opera-bench .opera-badge-mock')) !== null,
  );
await page.waitForSelector('.opera-bench select');
await page.select('.opera-bench-setup label:nth-of-type(3) select', '3');
await clickButton('Start game');
await waitPhase('guessing');
check(
  'the image is shown without any location text',
  await page
    .$eval('.opera-bench-image', (img) => img.naturalWidth > 0)
    .catch(() => false),
);
check(
  'truth is not in the round DOM while guessing',
  await page.evaluate(
    () =>
      !/Truth|game score/.test(
        document.querySelector('.opera-bench').textContent,
      ),
  ),
);

// Round 1: click the globe.
await page.mouse.click(420, 450);
await page.waitForFunction(
  () => window.__opera.store.get().benchmark.guess !== null,
  { timeout: 15000 },
);
check(
  'a globe click sets the guess and draws one marker',
  (await entityCount()) === 1,
);
await page.screenshot({ path: `${outDir}/bench-01-guess.png` });
await clickButton('Lock in guess');
await waitPhase('revealed');
const first = await page.evaluate(
  () => window.__opera.store.get().benchmark.result,
);
check(
  'reveal returns the truth and a user score',
  first.truth && first.user.score >= 0,
);
check(
  'reveal draws truth, guess, model markers plus two geodesic lines',
  (await entityCount()) >= 5,
);
check(
  'model kind is labelled',
  first.model.kind === (kind === 'mock' ? 'mock' : 'real') ||
    (kind === 'real' && ['mock', 'real'].includes(first.model.kind)),
);
check(
  'attribution and the licence-review caveat are shown',
  await page.evaluate(() =>
    /licence not yet reviewed/.test(
      document.querySelector('.opera-bench').textContent,
    ),
  ),
);
await new Promise((r) => setTimeout(r, 3000));
await page.screenshot({ path: `${outDir}/bench-02-reveal.png` });

// Round 2: type coordinates.
await clickButton('Next round');
await waitPhase('guessing');
check('the previous round markers are cleared', (await entityCount()) === 0);
await page.type('input[aria-label="Guess latitude"]', '10');
await page.type('input[aria-label="Guess longitude"]', '20');
await page.$eval('input[aria-label="Guess longitude"]', (e) =>
  e.dispatchEvent(new Event('change')),
);
await page.waitForFunction(
  () => window.__opera.store.get().benchmark.guess?.lat === 10,
  { timeout: 10000 },
);
await clickButton('Lock in guess');
await waitPhase('revealed');

// Round 3: skip.
await clickButton('Next round');
await waitPhase('guessing');
await clickButton('Skip');
await waitPhase('revealed');
const third = await page.evaluate(
  () => window.__opera.store.get().benchmark.result,
);
check('a skipped round has no user result', third.user === null);
await clickButton('Finish');
check(
  'summary compares the player and the model',
  await page.evaluate(() => {
    const t = document.querySelector('.opera-bench').textContent;
    return /Game over: 3 rounds/.test(t) && /Total game score/.test(t);
  }),
);
check('globe markers are cleared at the end', (await entityCount()) === 0);
await page.screenshot({ path: `${outDir}/bench-03-summary.png` });

await page.click('.opera-tab[data-mode="analyze"]');
check(
  'switching back shows the analyze panels again',
  await page.evaluate(
    () => !document.querySelector('.opera-mode-analyze').hidden,
  ),
);
console.log(
  'console/page errors:',
  errors.filter((e) => !/404/.test(e)),
);
await browser.close();
process.exit(Object.values(results).every(Boolean) ? 0 : 1);
