/**
 * Renders the lokate. collar scenes (lokate.html) to PNG:
 *   node marketing/product/render-lokate.cjs /tmp/lokate [only-this-shot]
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const OUT = path.resolve(process.argv[2] ?? path.join(__dirname, 'out-lokate'));
const ONLY = process.argv[3];
const SCENE = `file://${path.join(__dirname, 'lokate.html')}`;
const WIDE = { width: 2400, height: 1350 };
const TALL = { width: 1200, height: 1500 };

const SHOTS = {
  'hero-trio': [WIDE, { scene: 'trio', cam: [40, 80, 245], target: [22, 22, 0], fov: 28 }],
  'hero-collar': [WIDE, { scene: 'hero', cam: [150, 42, 110], target: [22, 10, 10], fov: 26, yaw: -0.35 }],
  'collar-closeup': [WIDE, { scene: 'hero', cam: [125, 28, 30], target: [30, 9, -14], fov: 24, yaw: 0.15 }],
  'back-floating': [WIDE, { scene: 'float-back', cam: [10, 80, 120], target: [0, 32, 0], fov: 24 }],
  'side-floating': [WIDE, { scene: 'float-side', cam: [0, 52, 135], target: [0, 40, 0], fov: 22 }],
  'top-led': [WIDE, { scene: 'top', cam: [8, 110, 46], target: [0, 0, 0], fov: 26 }],
  charger: [WIDE, { scene: 'charger', cam: [80, 85, 110], target: [-6, 6, -6], fov: 28 }],
  'card-collar': [TALL, { scene: 'hero', cam: [150, 70, 125], target: [22, 26, 8], fov: 34, yaw: -0.35 }],
  'card-back': [TALL, { scene: 'float-back', cam: [10, 95, 135], target: [0, 50, 0], fov: 30 }],
  'card-charger': [TALL, { scene: 'charger', cam: [75, 120, 120], target: [-4, 30, -6], fov: 34 }],
  'card-top': [TALL, { scene: 'top', cam: [6, 150, 60], target: [0, 22, -18], fov: 30 }],
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--allow-file-access-from-files'] });
  const page = await browser.newPage();
  page.on('pageerror', (e) => console.error('pageerror', e.message));
  page.on('console', (m) => m.type() === 'error' && console.error(m.text()));
  for (const [name, [size, opts]] of Object.entries(SHOTS)) {
    if (ONLY && name !== ONLY) continue;
    await page.setViewportSize(size);
    await page.goto(`${SCENE}#${encodeURIComponent(JSON.stringify(opts))}`);
    await page.reload();
    await page.waitForFunction(() => window.__rendered === true, null, { timeout: 120_000 });
    await page.screenshot({ path: path.join(OUT, `${name}.png`) });
    console.log('rendered', name);
  }
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
