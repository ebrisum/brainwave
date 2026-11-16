/**
 * Renders the product scenes in scene.html (Three.js, headless Chromium) to
 * transparent PNGs:   node marketing/product/render.cjs marketing/product/out
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const OUT = path.resolve(process.argv[2] ?? path.join(__dirname, 'out'));
const SCENE = `file://${path.join(__dirname, 'scene.html')}`;

const SHOTS = {
  'collar-white-coral': { scene: 'hero', pod: '#F4F5F7', strap: '#E8735A', cam: [120, 75, 150], target: [10, 18, 0] },
  'collar-ink-blue': { scene: 'hero', pod: '#141A24', strap: '#2449E8', cam: [120, 75, 150], target: [10, 18, 0] },
  'collar-white-sage': { scene: 'hero', pod: '#F4F5F7', strap: '#7FA88C', cam: [120, 75, 150], target: [10, 18, 0] },
  'pod-closeup': { scene: 'pod', pod: '#F4F5F7', cam: [30, 70, 75], target: [0, 9, 0], fov: 26 },
  'pod-closeup-ink': { scene: 'pod', pod: '#141A24', cam: [30, 70, 75], target: [0, 9, 0], fov: 26 },
  'size-coin': { scene: 'coin', pod: '#F4F5F7', cam: [0, 120, 70], target: [4, 0, 2], fov: 28 },
  charger: { scene: 'charger', pod: '#F4F5F7', cam: [85, 95, 120], target: [-12, 4, -12], fov: 30 },
  colors: {
    scene: 'colors',
    colors: [['#F4F5F7', '#E8735A'], ['#141A24', '#2449E8'], ['#F4F5F7', '#7FA88C'], ['#F4F5F7', '#141A24']],
    cam: [0, 170, 420], target: [0, 14, 0], fov: 32,
  },
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--allow-file-access-from-files'] });
  const page = await browser.newPage({ viewport: { width: 2000, height: 1500 } });
  page.on('pageerror', (e) => console.error('pageerror', e.message));
  page.on('console', (m) => m.type() === 'error' && console.error(m.text()));
  for (const [name, opts] of Object.entries(SHOTS)) {
    const size = name === 'colors' ? { width: 2400, height: 1200 } : { width: 2000, height: 1500 };
    await page.setViewportSize(size);
    await page.goto(`${SCENE}#${encodeURIComponent(JSON.stringify(opts))}`);
    await page.reload();
    await page.waitForFunction(() => window.__rendered === true, null, { timeout: 60_000 });
    await page.screenshot({ path: path.join(OUT, `${name}.png`), omitBackground: true });
    console.log('rendered', name);
  }
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
