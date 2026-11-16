/**
 * Turns the raw screens from capture.cjs into website material:
 *   framed/<lang>/<screen>.png   the screen in a phone, transparent background
 *   cards/<lang>/<nn>-<screen>.jpg  4:5 card with headline and phone (sections, social)
 *   hero-<lang>.jpg               wide banner with three phones
 *   node marketing/compose.cjs marketing/raw marketing
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const RAW = path.resolve(process.argv[2] ?? path.join(__dirname, 'raw'));
const OUT = path.resolve(process.argv[3] ?? __dirname);
const FONTS = path.resolve(__dirname, '../app/node_modules/@expo-google-fonts');

const COPY = {
  nl: {
    '01-map': ['Al je katten op één kaart', 'Live via het mobiele netwerk, ook als je kat ver van je telefoon is.'],
    '04-cat': ['Weet of je kat thuis is', 'Een melding zodra je kat van huis gaat of terugkomt.'],
    '05-route': ['Bekijk elke route terug', 'Speel de dag af en zie precies waar je kat is geweest.'],
    '06-heatmap': ['Ontdek de lievelingsplekjes', 'Waar je kat de meeste tijd doorbrengt, in één oogopslag.'],
    '07-history': ['Zijn dag als tijdlijn', 'Thuis, op pad en waar hij even bleef liggen.'],
    '08-insights': ['Hoe actief is je kat?', 'Afstand, actieve tijd en nachtelijke uitstapjes per week.'],
    '10-lost': ['Vermist? Iedereen zoekt mee', 'Live link voor de buren, een poster en een kompas.'],
    '11-alerts': ['Alleen meldingen die ertoe doen', "Stille uren 's nachts. Vermist komt altijd door."],
  },
  en: {
    '01-map': ['All your cats on one map', 'Live over the mobile network, even far from your phone.'],
    '04-cat': ['Know if your cat is home', 'An alert the moment your cat leaves or comes back.'],
    '05-route': ['Replay every route', 'Play back the day and see exactly where your cat went.'],
    '06-heatmap': ['Discover the favourite spots', 'Where your cat spends its time, at a glance.'],
    '07-history': ['The day as a timeline', 'At home, out and about, and where it stopped for a nap.'],
    '08-insights': ['How active is your cat?', 'Distance, active time and night outings, week by week.'],
    '10-lost': ['Lost? Everyone helps search', 'A live link for the neighbours, a poster and a compass.'],
    '11-alerts': ['Only alerts that matter', 'Quiet hours at night. Lost mode always comes through.'],
  },
};
const HERO = { nl: ['Weet altijd waar je kat is', 'Gps-halsband van 19 gram. Geen abonnement, ooit.'], en: ['Always know where your cat is', 'A 19-gram GPS collar. No subscription, ever.'] };
const HERO_SCREENS = ['05-route', '01-map', '10-lost'];

const fontFace = `
@font-face { font-family: Display; src: url(file://${FONTS}/bricolage-grotesque/700Bold/BricolageGrotesque_700Bold.ttf); }
@font-face { font-family: Body; src: url(file://${FONTS}/geist/500Medium/Geist_500Medium.ttf); }
@font-face { font-family: BodyBold; src: url(file://${FONTS}/geist/600SemiBold/Geist_600SemiBold.ttf); }`;

/** A phone (status bar + screen in a black bezel). `w` is the screen width in px. */
const phone = (img, w) => {
  const s = w / 390; // the screen was 390 pt wide
  return `<div class="phone" style="width:${w + 28 * s}px;padding:${14 * s}px;border-radius:${62 * s}px">
    <div class="screen" style="border-radius:${48 * s}px">
      <div class="status" style="height:${47 * s}px;font-size:${16 * s}px;padding:0 ${30 * s}px">
        <span>9:41</span>
        <span class="island" style="width:${120 * s}px;height:${34 * s}px;top:${10 * s}px;margin-left:-${60 * s}px"></span>
        <svg width="${70 * s}" height="${14 * s}" viewBox="0 0 70 14"><g fill="#0C1220">
          <rect x="0" y="9" width="3" height="5" rx="1"/><rect x="5" y="6" width="3" height="8" rx="1"/><rect x="10" y="3" width="3" height="11" rx="1"/><rect x="15" y="0" width="3" height="14" rx="1"/>
          <path d="M31 4.5a10 10 0 0 1 13 0l-1.6 1.7a7.6 7.6 0 0 0-9.8 0zM34 8a5.6 5.6 0 0 1 7 0l-1.7 1.8a3 3 0 0 0-3.6 0zM37.5 11.5l1-1 1 1-1 1z"/>
          <rect x="48" y="1.5" width="19" height="11" rx="3" fill="none" stroke="#0C1220" stroke-width="1.2" opacity=".5"/><rect x="50" y="3.5" width="13" height="7" rx="1.5"/><rect x="68" y="5" width="1.6" height="4" rx=".8" opacity=".5"/></g></svg>
      </div>
      <img src="file://${img}" style="width:${w}px;display:block"/>
    </div>
  </div>`;
};

const page = (body, w, h, bg) => `<!doctype html><html><head><meta charset="utf-8"><style>${fontFace}
  * { box-sizing: border-box; margin: 0; }
  html, body { width: ${w}px; height: ${h}px; background: ${bg}; overflow: hidden; }
  .phone { background: #0C1220; box-shadow: 0 40px 80px rgba(12,18,32,.28), 0 0 0 2px #2b3343 inset; }
  .screen { overflow: hidden; background: #F3F5F8; position: relative; }
  .status { display: flex; align-items: center; justify-content: space-between; background: #F3F5F8; font-family: BodyBold; color: #0C1220; position: relative; }
  .island { position: absolute; left: 50%; background: #000; border-radius: 999px; }
  h1 { font-family: Display; color: #0C1220; letter-spacing: -0.02em; line-height: 1.02; }
  p { font-family: Body; color: #5B6577; line-height: 1.35; }
  .brand { font-family: Display; color: #2449E8; letter-spacing: .02em; }
</style></head><body>${body}</body></html>`;

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ deviceScaleFactor: 1 });
  const tmp = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'compose-'));
  const render = async (html, w, h, file, transparent = false) => {
    const p = await ctx.newPage({ viewport: { width: w, height: h } });
    const f = path.join(tmp, 'p.html');
    fs.writeFileSync(f, html);
    await p.setViewportSize({ width: w, height: h });
    await p.goto(`file://${f}`);
    await p.evaluate(() => document.fonts.ready);
    await p.waitForTimeout(150);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    await p.screenshot({ path: file, omitBackground: transparent, type: file.endsWith('.jpg') ? 'jpeg' : 'png', ...(file.endsWith('.jpg') ? { quality: 88 } : {}) });
    await p.close();
  };

  for (const lang of ['nl', 'en']) {
    const dir = path.join(RAW, lang);
    for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.png'))) {
      const name = f.replace('.png', '');
      const img = path.join(dir, f);
      // Framed phone, transparent (1170 px screen = native iPhone width).
      const W = 1170;
      const fw = W + 28 * 3, fh = Math.round((797 + 47) * 3 + 28 * 3);
      await render(page(`<div style="padding:40px">${phone(img, W)}</div>`, fw + 80, fh + 80, 'transparent'), fw + 80, fh + 80, path.join(OUT, 'framed', lang, `${name}.png`), true);
    }
    // 4:5 cards: headline on top, phone below (cropped by the card edge).
    let n = 1;
    for (const [name, [title, sub]] of Object.entries(COPY[lang])) {
      const img = path.join(dir, `${name}.png`);
      const body = `<div style="height:100%;background:linear-gradient(160deg,#E7EDFF 0%,#F3F5F8 55%,#FFFFFF 100%);display:flex;flex-direction:column;align-items:center;padding:96px 90px 0;gap:22px;overflow:hidden">
        <div class="brand" style="font-size:26px">CAT TRACKER</div>
        <h1 style="font-size:84px;text-align:center">${title}</h1>
        <p style="font-size:34px;text-align:center;max-width:900px">${sub}</p>
        <div style="margin-top:40px">${phone(img, 640)}</div></div>`;
      await render(page(body, 1200, 1500, '#F3F5F8'), 1200, 1500, path.join(OUT, 'cards', lang, `${String(n++).padStart(2, '0')}-${name}.jpg`));
    }
    // Wide hero with three phones.
    const [title, sub] = HERO[lang];
    const phones = HERO_SCREENS.map((s, i) => `<div style="margin-top:${i === 1 ? 0 : 110}px">${phone(path.join(dir, `${s}.png`), i === 1 ? 470 : 420)}</div>`).join('');
    const body = `<div style="height:100%;display:flex;align-items:center;gap:70px;padding:0 110px;background:linear-gradient(120deg,#0C1220 0%,#1B2547 100%);overflow:hidden">
      <div style="flex:0 0 700px;display:flex;flex-direction:column;gap:28px">
        <div class="brand" style="font-size:28px;color:#7D9BFF">CAT TRACKER</div>
        <h1 style="font-size:96px;color:#EEF2F8">${title}</h1>
        <p style="font-size:38px;color:#97A1B2">${sub}</p>
      </div>
      <div style="display:flex;gap:30px;align-items:flex-start;margin-top:330px">${phones}</div></div>`;
    await render(page(body, 2400, 1260, '#0C1220'), 2400, 1260, path.join(OUT, `hero-${lang}.jpg`));
  }
  await browser.close();
  console.log('composed into', OUT);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
