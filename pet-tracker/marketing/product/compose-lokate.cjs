/**
 * lokate. cards and banners from the renders (render-lokate.cjs):
 *   node marketing/product/compose-lokate.cjs <renders dir> <out dir>
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const R = path.resolve(process.argv[2] ?? path.join(__dirname, 'out-lokate'));
const OUT = path.resolve(process.argv[3] ?? path.join(__dirname, '../lokate'));
const FONTS = path.resolve(__dirname, '../../app/node_modules/@expo-google-fonts');
const GREEN = '#2F4A2C';
const BG = '#E8DCCB';

const CARDS = {
  nl: [
    ['card-collar', 'Weet altijd waar je kat is', '19 gram. Geen abonnement, ooit.'],
    ['card-top', 'Gemaakt voor katten', 'Licht, glad en zonder scherpe randen.'],
    ['card-back', 'Magnetisch opladen', 'Drie contacten. Leg hem neer en hij laadt.'],
    ['card-charger', 'Opladen? Leg hem neer.', 'Het lampje laat zien wanneer hij vol is.'],
  ],
  en: [
    ['card-collar', 'Always know where your cat is', '19 grams. No subscription, ever.'],
    ['card-top', 'Made for cats', 'Light, smooth and no sharp edges.'],
    ['card-back', 'Magnetic charging', 'Three contacts. Put it down and it charges.'],
    ['card-charger', 'Charging? Just put it down.', 'The light shows when it is full.'],
  ],
};
const BANNER = {
  nl: ['Weet altijd waar je kat is', 'De lichte gps-halsband voor katten. 19 gram, geen abonnement.'],
  en: ['Always know where your cat is', 'The light GPS collar for cats. 19 grams, no subscription.'],
};

const css = `
@font-face { font-family: Display; src: url(file://${FONTS}/geist/600SemiBold/Geist_600SemiBold.ttf); }
@font-face { font-family: Body; src: url(file://${FONTS}/geist/400Regular/Geist_400Regular.ttf); }
* { box-sizing: border-box; margin: 0; }
html, body { background: ${BG}; overflow: hidden; }
.mark { font-family: Display; color: ${GREEN}; letter-spacing: -0.02em; }
h1 { font-family: Display; color: ${GREEN}; letter-spacing: -0.03em; line-height: 1.02; }
p { font-family: Body; color: #6B5E4C; line-height: 1.35; }`;

(async () => {
  const browser = await chromium.launch();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'lokate-'));
  const render = async (body, w, h, file) => {
    const p = await browser.newPage({ viewport: { width: w, height: h } });
    const f = path.join(tmp, 'p.html');
    fs.writeFileSync(f, `<!doctype html><html><head><meta charset="utf-8"><style>${css} html,body{width:${w}px;height:${h}px}</style></head><body>${body}</body></html>`);
    await p.goto(`file://${f}`);
    await p.evaluate(() => document.fonts.ready);
    await p.waitForTimeout(150);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    await p.screenshot({ path: file, type: 'jpeg', quality: 92 });
    await p.close();
  };

  for (const lang of ['nl', 'en']) {
    for (const [i, [shot, title, sub]] of CARDS[lang].entries()) {
      const body = `<div style="position:relative;width:1200px;height:1500px">
        <img src="file://${path.join(R, `${shot}.png`)}" style="position:absolute;inset:0;width:1200px;height:1500px"/>
        <div style="position:absolute;top:0;left:0;right:0;height:520px;background:linear-gradient(${BG} 55%, rgba(232,220,203,0))"></div>
        <div style="position:absolute;top:90px;left:90px;right:90px;display:flex;flex-direction:column;gap:22px">
          <div class="mark" style="font-size:40px">lokate.</div>
          <h1 style="font-size:88px">${title}</h1>
          <p style="font-size:36px">${sub}</p>
        </div></div>`;
      await render(body, 1200, 1500, path.join(OUT, 'cards', lang, `${String(i + 1).padStart(2, '0')}-${shot.replace('card-', '')}.jpg`));
    }
    const [title, sub] = BANNER[lang];
    const body = `<div style="position:relative;width:2400px;height:1350px">
      <img src="file://${path.join(R, 'hero-collar.png')}" style="position:absolute;left:700px;top:110px;width:2000px;height:1125px"/>
      <div style="position:absolute;inset:0;background:linear-gradient(90deg, ${BG} 30%, rgba(232,220,203,0) 52%)"></div>
      <div style="position:absolute;left:130px;top:0;bottom:0;width:760px;display:flex;flex-direction:column;justify-content:center;gap:30px">
        <div class="mark" style="font-size:48px">lokate.</div>
        <h1 style="font-size:96px">${title}</h1>
        <p style="font-size:42px">${sub}</p>
      </div></div>`;
    await render(body, 2400, 1350, path.join(OUT, `banner-${lang}.jpg`));
  }
  // Wide renders without text, for the website builder.
  for (const f of fs.readdirSync(R).filter((x) => x.endsWith('.png') && !x.startsWith('card-'))) {
    const body = `<img src="file://${path.join(R, f)}" style="width:2400px;height:1350px;display:block"/>`;
    await render(body, 2400, 1350, path.join(OUT, 'photos', f.replace('.png', '.jpg')));
  }
  await browser.close();
  console.log('composed into', OUT);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
