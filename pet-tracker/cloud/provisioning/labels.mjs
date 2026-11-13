/** Claim links and a printable label sheet (pure, so it can be tested). */
import QRCode from 'qrcode';

/** Opens the app's "Add cat" screen with the collar and code filled in. */
export function claimLink(deviceUid, claimCode) {
  return `cattracker://add-cat?device=${encodeURIComponent(deviceUid)}&code=${encodeURIComponent(claimCode)}`;
}

/** "ABCD-EFGH-JKLM": easier to type from a label. */
export const prettyClaimCode = (code) => code.match(/.{1,4}/g).join('-');

const escape = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

export async function labelSheet(rows) {
  const labels = await Promise.all(
    rows.map(async (r) => {
      const svg = await QRCode.toString(claimLink(r.deviceUid, r.claimCode), { type: 'svg', margin: 0, errorCorrectionLevel: 'M' });
      return `<div class="label">${svg}<div><b>Cat Tracker</b><br>Scan to add your cat<br>
<span>Collar ID</span> ${escape(r.deviceUid)}<br><span>Code</span> ${escape(prettyClaimCode(r.claimCode))}</div></div>`;
    }),
  );
  return `<!doctype html><meta charset="utf-8"><title>Tracker labels</title>
<style>
  body { font: 11px/1.4 system-ui, sans-serif; margin: 10mm; }
  .sheet { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4mm; }
  .label { display: flex; gap: 3mm; align-items: center; border: 1px dashed #bbb; padding: 3mm; break-inside: avoid; }
  .label svg { width: 22mm; height: 22mm; flex: none; }
  span { color: #666; }
</style>
<div class="sheet">${labels.join('\n')}</div>`;
}

/** "imei[,model[,iccid]]" lines; a header line and blank lines are skipped. */
export function parseTrackerCsv(text) {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !/^(imei|device)/i.test(l))
    .map((l) => {
      const [deviceUid, model, iccid] = l.split(/[,;\t]/).map((c) => c.trim());
      if (!/^[A-Za-z0-9_-]{3,64}$/.test(deviceUid ?? '')) throw new Error(`Not a tracker id: "${l}"`);
      return { deviceUid, model: model || null, iccid: iccid || null };
    });
}
