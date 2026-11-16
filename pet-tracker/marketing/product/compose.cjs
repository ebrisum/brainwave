/**
 * Product cards and a collar + app banner from the renders (render.cjs) and
 * the app screens (../capture.cjs):
 *   node marketing/product/compose.cjs <renders dir> <app raw dir> <out dir>
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const RENDERS = path.resolve(process.argv[2] ?? path.join(__dirname, 'out'));
const RAW = path.resolve(process.argv[3] ?? path.join(__dirname, '../raw'));
const OUT = path.resolve(process.argv[4] ?? path.join(__dirname, '..'));
const FONTS = path.resolve(__dirname, '../../app/node_modules/@expo-google-fonts');

const CARDS = {
  nl: [
    ['collar-white-coral', '19 gram. Je kat merkt hem nauwelijks.', 'Lichter dan een AA-batterij, op een veiligheidshalsband die losschiet als hij ergens blijft haken.'],
    ['pod-closeup', 'Geen abonnement, ooit', 'Tien jaar mobiel netwerk zit in de prijs. Je betaalt één keer.'],
    ['collar-ink-blue', 'Altijd verbonden', 'Gps en het mobiele netwerk, ook als je kat ver van huis is.', 'dark'],
    ['charger', 'Opladen? Leg hem neer.', 'Op het laadstation. Het lampje laat zien wanneer hij vol is.'],
    ['colors', 'Kies je kleur', 'Een halsband die bij je kat past.'],
    ['size-coin', 'Klein genoeg voor elke kat', 'Nauwelijks groter dan een munt van 2 euro.'],
  ],
  en: [
    ['collar-white-coral', '19 grams. Your cat barely notices.', 'Lighter than an AA battery, on a breakaway collar that releases if it gets caught.'],
    ['pod-closeup', 'No subscription, ever', 'Ten years of mobile network included. You pay once.'],
    ['collar-ink-blue', 'Always connected', 'GPS and the mobile network, even far from home.', 'dark'],
    ['charger', 'Charging? Just put it down.', 'On the charging base. The light shows when it is full.'],
    ['colors', 'Pick a colour', 'A collar that suits your cat.'],
    ['size-coin', 'Small enough for any cat', 'Barely bigger than a 2-euro coin.'],
  ],
};
const HERO = {
  nl: ['Weet altijd waar je kat is', 'Halsband van 19 gram en een app. Geen abonnement, ooit.'],
  en: ['Always know where your cat is', 'A 19-gram collar and an app. No subscription, ever.'],
};

const css = `
@font-face { font-family: Display; src: url(file://${FONTS}/bricolage-grotesque/700Bold/BricolageGrotesque_700Bold.ttf); }
@font-face { font-family: Body; src: url(file://${FONTS}/geist/500Medium/Geist_500Medium.ttf); }
@font-face { font-family: BodyBold; src: url(file://${FONTS}/geist/600SemiBold/Geist_600SemiBold.ttf); }
* { box-sizing: border-box; margin: 0; }
h1 { font-family: Display; letter-spacing: -0.02em; line-height: 1.02; }
p { font-family: Body; line-height: 1.35; }
.brand { font-family: Display; letter-spacing: .02em; }
.phone { background: #0C1220; box-shadow: 0 40px 80px rgba(0,0,0,.35), 0 0 0 2px #2b3343 inset; }
.screen { overflow: hidden; background: #F3F5F8; }
.status { display: flex; align-items: center; justify-content: space-between; background: #F3F5F8; font-family: BodyBold; color: #0C1220; position: relative; }
.island { position: absolute; left: 50%; background: #000; border-radius: 999px; }`;

const phone = (img, w) => {
  const s = w / 390;
  return `<div class="phone" style="width:${w + 28 * s}px;padding:${14 * s}px;border-radius:${62 * s}px">
    <div class="screen" style="border-radius:${48 * s}px">
      <div class="status" style="height:${47 * s}px;font-size:${16 * s}px;padding:0 ${30 * s}px"><span>9:41</span>
        <span class="island" style="width:${120 * s}px;height:${34 * s}px;top:${10 * s}px;margin-left:-${60 * s}px"></span><span>●●●</span></div>
      <img src="file://${img}" style="width:${w}px;display:block"/></div></div>`;
};

(async () => {
  const browser = await chromium.launch();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'product-'));
  const render = async (body, w, h, file) => {
    const p = await browser.newPage({ viewport: { width: w, height: h } });
    const f = path.join(tmp, 'p.html');
    fs.writeFileSync(f, `<!doctype html><html><head><meta charset="utf-8"><style>${css} html,body{width:${w}px;height:${h}px;overflow:hidden}</style></head><body>${body}</body></html>`);
    await p.goto(`file://${f}`);
    await p.evaluate(() => document.fonts.ready);
    await p.waitForTimeout(150);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    await p.screenshot({ path: file, type: 'jpeg', quality: 90 });
    await p.close();
  };

  for (const lang of ['nl', 'en']) {
    for (const [i, [shot, title, sub, tone]] of CARDS[lang].entries()) {
      const dark = tone === 'dark';
      const bg = dark ? 'radial-gradient(circle at 50% 70%, #24305A 0%, #0C1220 70%)' : 'radial-gradient(circle at 50% 72%, #FFFFFF 0%, #EEF1F7 55%, #E2E8F5 100%)';
      const wide = shot === 'colors';
      const body = `<div style="height:100%;background:${bg};display:flex;flex-direction:column;align-items:center;padding:96px 80px 40px;gap:22px;overflow:hidden">
        <div class="brand" style="font-size:26px;color:${dark ? '#7D9BFF' : '#2449E8'}">CAT TRACKER</div>
        <h1 style="font-size:80px;text-align:center;color:${dark ? '#EEF2F8' : '#0C1220'}">${title}</h1>
        <p style="font-size:33px;text-align:center;max-width:960px;color:${dark ? '#97A1B2' : '#5B6577'}">${sub}</p>
        <div style="flex:1;width:100%;display:flex;align-items:center;justify-content:center;overflow:visible">
          <img src="file://${path.join(RENDERS, `${shot}.png`)}" style="width:${wide ? 1180 : 1300}px;margin-top:${wide ? 0 : -60}px"/></div></div>`;
      await render(body, 1200, 1500, path.join(OUT, 'product-cards', lang, `${String(i + 1).padStart(2, '0')}-${shot}.jpg`));
    }
    const [title, sub] = HERO[lang];
    const body = `<div style="height:100%;display:flex;align-items:center;padding:0 110px;background:radial-gradient(circle at 62% 60%, #24305A 0%, #0C1220 65%);overflow:hidden;position:relative">
      <div style="flex:0 0 720px;display:flex;flex-direction:column;gap:28px;z-index:2">
        <div class="brand" style="font-size:28px;color:#7D9BFF">CAT TRACKER</div>
        <h1 style="font-size:100px;color:#EEF2F8">${title}</h1>
        <p style="font-size:38px;color:#97A1B2">${sub}</p>
      </div>
      <img src="file://${path.join(RENDERS, 'collar-ink-blue.png')}" style="position:absolute;left:780px;top:330px;width:1080px"/>
      <div style="position:absolute;right:120px;top:120px">${phone(path.join(RAW, lang, '01-map.png'), 440)}</div></div>`;
    await render(body, 2400, 1260, path.join(OUT, `hero-collar-${lang}.jpg`));
  }
  await browser.close();
  console.log('composed into', OUT);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
