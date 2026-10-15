// Browser smoke test of the OPERA shell in mock mode. Usage:
//   VITE_OPERA_MOCK=1 npm run dev -- --port 4180 &   then   node tests/opera/e2e/mock-ui.mjs http://localhost:4180 /tmp/shots
import { mkdirSync } from 'node:fs';
import puppeteer from 'puppeteer';
import sharp from 'sharp';

const [url = 'http://localhost:4173', outDir = '/tmp/opera-shots'] =
  process.argv.slice(2);
mkdirSync(outDir, { recursive: true });
const jpeg = await sharp({
  create: {
    width: 640,
    height: 480,
    channels: 3,
    background: { r: 90, g: 140, b: 100 },
  },
})
  .jpeg()
  .toBuffer();
const jpegPath = `${outDir}/test-photo.jpg`;
await (await import('node:fs/promises')).writeFile(jpegPath, jpeg);

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
  'mock badge visible',
  await page.$eval(
    '.opera-header .opera-badge-mock',
    (e) => e.textContent === 'MOCK DATA',
  ),
);
await (await page.$('.opera-root input[type=file]')).uploadFile(jpegPath);
await page.waitForSelector('.opera-preview img');
check('preview shown', true);
check(
  'analyze disabled before attestation',
  await page.$eval('.opera-btn-primary', (b) => b.disabled),
);
await page.click('#opera-rights');
check(
  'analyze enabled after attestation',
  await page.$eval('.opera-btn-primary', (b) => !b.disabled),
);
await page.click('.opera-btn-primary');
await page
  .waitForSelector('.opera-candidate', { timeout: 15000 })
  .catch(async (error) => {
    console.log(
      'DIAG',
      JSON.stringify(
        await page.evaluate(() => {
          const {
            status,
            error: err,
            analysis,
            rightsAttested,
          } = window.__opera.store.get();
          const b = document.querySelector('.opera-btn-primary');
          const r = b.getBoundingClientRect();
          const top = document.elementFromPoint(
            r.x + r.width / 2,
            r.y + r.height / 2,
          );
          return {
            status,
            err,
            analysis: !!analysis,
            rightsAttested,
            btn: b.textContent,
            top: top?.tagName + '.' + top?.className,
          };
        }),
      ),
    );
    throw error;
  });
check('5 candidates', (await page.$$('.opera-candidate')).length === 5);
check('clues grouped', (await page.$$('.opera-clue-group')).length >= 2);
check(
  'globe entities (5 markers)',
  (await page.evaluate(
    () =>
      window.__godsEyeView.viewer.dataSources.getByName('opera-candidates')[0]
        .entities.values.length,
  )) === 5,
);
await new Promise((r) => setTimeout(r, 3500));
await page.screenshot({ path: `${outDir}/01-analyzed.png` });
const before = await page.evaluate(
  () => window.__godsEyeView.viewer.camera.positionCartographic.height,
);
await page.evaluate(() =>
  document.querySelectorAll('.opera-candidate .opera-btn')[2].click(),
);
await new Promise((r) => setTimeout(r, 4500));
const after = await page.evaluate(
  () => window.__godsEyeView.viewer.camera.positionCartographic.height,
);
check('fly-to moved the camera', Math.abs(after - before) > 1000);
check(
  'active candidate highlighted',
  await page.$eval(
    '.opera-candidate.is-active .opera-rank',
    (e) => e.textContent === '3',
  ),
);
await page.screenshot({ path: `${outDir}/02-flyto.png` });
check(
  'upstream viewer still has its own data sources',
  await page.evaluate(
    () => window.__godsEyeView.viewer.dataSources.length >= 2,
  ),
);
await page.click('.opera-collapse');
check(
  'panel collapses to launcher',
  await page.$eval('.opera-launcher', (e) => !e.hidden),
);
await page.evaluate(() => window.__opera.destroy());
check(
  'overlays removed on destroy and upstream layers untouched',
  await page.evaluate(() => {
    const ds = window.__godsEyeView.viewer.dataSources;
    const opera = ds.getByName('opera-candidates')[0];
    return (!opera || opera.entities.values.length === 0) && ds.length >= 1;
  }),
);
console.log(
  'console/page errors:',
  errors.filter((e) => !/404/.test(e)),
);
await browser.close();
process.exit(Object.values(results).every(Boolean) ? 0 : 1);
