/**
 * App impressions for the website: drives the web build of the app in demo
 * mode (Playwright, phone viewport at 3x) and saves raw screens per language.
 *   cd app && npx expo export -p web --output-dir /tmp/web && npx serve -s /tmp/web -l 8090
 *   node marketing/capture.cjs http://localhost:8090 marketing/raw
 * Then: node marketing/compose.cjs (phone frames + headlines).
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.argv[2] ?? 'http://localhost:8090';
const OUT = process.argv[3] ?? path.join(__dirname, 'raw');
// iPhone-sized screen below a 47 pt status bar (drawn by compose.cjs).
const VIEW = { width: 390, height: 797 };

(async () => {
  const browser = await chromium.launch();
  const problems = [];
  for (const lang of ['nl', 'en']) {
    const nl = lang === 'nl';
    const dir = path.join(OUT, lang);
    fs.mkdirSync(dir, { recursive: true });
    const ctx = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 3, locale: nl ? 'nl-NL' : 'en-GB', colorScheme: 'light', timezoneId: 'Europe/Amsterdam' });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => problems.push(`${lang}: ${e.message}`));
    const settle = (ms = 1600) => page.waitForTimeout(ms);
    // Website shots: the demo reads like a real account (no "Demo" labels).
    const unDemo = () =>
      page.evaluate((nl) => {
        const swap = nl
          ? { 'Demo · gesimuleerde posities': 'Bijgewerkt zojuist', Demohuishouden: 'Ons huis', Demohalsband: 'Cat Tracker-halsband', DEMOHUISHOUDEN: 'ONS HUIS' }
          : { 'Demo · simulated positions': 'Updated just now', 'Demo household': 'Our home', 'Demo collar': 'Cat Tracker collar', 'DEMO HOUSEHOLD': 'OUR HOME' };
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
          const v = n.nodeValue.trim();
          if (swap[v]) n.nodeValue = swap[v];
          else if (v === 'Demo' && n.parentElement) {
            let el = n.parentElement;
            while (el.parentElement && el.parentElement.textContent.trim() === 'Demo') el = el.parentElement;
            el.style.display = 'none';
          }
        }
      }, nl);
    const shot = async (name) => {
      await page.waitForLoadState('networkidle').catch(() => {});
      await settle(900);
      await unDemo();
      await settle(100);
      await page.screenshot({ path: path.join(dir, `${name}.png`) });
    };
    const button = (re) => page.getByRole('button', { name: re }).last();
    const tab = (name) => page.getByRole('tab', { name: new RegExp(`${name}$`) }).first().click();

    await page.goto(BASE);
    await settle(2500);
    await page.getByRole('button', { name: nl ? 'Overslaan' : 'Skip' }).click();
    await settle(800);
    await page.getByText(nl ? /Probeer de demo/ : /Try the demo/).first().click();
    await settle(3000);

    await shot('01-map');
    // Tap a cat on the map: its card with the photo, place and directions.
    await page.getByRole('button', { name: 'Tijger', exact: true }).first().click().catch(() => {});
    await shot('02-map-selected');

    await tab(nl ? 'Katten' : 'Cats');
    await shot('03-cats');

    await button(nl ? /^Tijger openen$/ : /^Open Tijger$/).click();
    await settle();
    await shot('04-cat');

    await page.getByRole('button', { name: 'Route', exact: true }).first().click();
    await settle(2000);
    await shot('05-route');
    await page.getByRole('button', { name: nl ? 'Hittekaart' : 'Heatmap', exact: true }).last().click();
    await settle(2000);
    await shot('06-heatmap');
    await page.getByRole('button', { name: 'Live', exact: true }).last().click();
    await settle();

    await button(new RegExp(`${nl ? 'Geschiedenis' : 'History'}$`)).click();
    await settle(2200);
    await shot('07-history');
    await page.goBack();
    await settle();
    await button(new RegExp(`${nl ? 'Inzichten' : 'Insights'}$`)).click();
    await settle(2000);
    await shot('08-insights');
    await page.goBack();
    await settle();
    await button(new RegExp(`${nl ? 'Halsband' : 'Collar'}$`)).click();
    await settle(2000);
    await shot('09-collar');
    await page.goBack();
    await settle();

    page.once('dialog', (d) => d.accept());
    await button(nl ? 'Vermist-modus aanzetten voor Tijger' : 'Turn on lost mode for Tijger').click();
    await settle(2200);
    await shot('10-lost');
    await page.goBack();
    await settle();
    await page.goBack();
    await settle();

    await tab(nl ? 'Meldingen' : 'Alerts');
    await shot('11-alerts');
    await tab(nl ? 'Plekken' : 'Places');
    await settle(1500);
    await shot('12-places');
    await tab(nl ? 'Kaart' : 'Map');
    await shot('13-map-lost');
    await ctx.close();
  }
  await browser.close();
  console.log(problems.length ? problems.join('\n') : 'captured without errors');
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
