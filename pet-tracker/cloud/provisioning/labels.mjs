/** Claim links and a printable label sheet (pure, so it can be tested). */
import QRCode from 'qrcode';

/** Opens the app's "Add cat" screen with the collar and code filled in. */
export function claimLink(deviceUid, claimCode) {
  return `cattracker://add-cat?device=${encodeURIComponent(deviceUid)}&code=${encodeURIComponent(claimCode)}`;
}

/** "ABCD-EFGH-JKLM": easier to type from a label. */
export const prettyClaimCode = (code) => code.match(/.{1,4}/g).join('-');

const escape = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

/** One PNG per tracker, for a label or packaging printer. */
export async function labelPng(deviceUid, claimCode) {
  return QRCode.toBuffer(claimLink(deviceUid, claimCode), { type: 'png', width: 600, margin: 2, errorCorrectionLevel: 'M' });
}

export async function labelSheet(rows) {
  const labels = await Promise.all(
    rows.map(async (r) => {
      const svg = await QRCode.toString(claimLink(r.deviceUid, r.claimCode), { type: 'svg', margin: 0, errorCorrectionLevel: 'M' });
      return `<div class="label">${svg}<div class="text"><b>Cat Tracker</b>
<div class="hint">Open the app → Add cat → GPS collar → Scan</div>
<div><span>Collar ID</span><code>${escape(r.deviceUid)}</code></div>
<div><span>Code</span><code>${escape(prettyClaimCode(r.claimCode))}</code></div></div></div>`;
    }),
  );
  return `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Tracker labels</title>
<style>
  @page { size: A4; margin: 10mm; }
  body { font: 9pt/1.35 system-ui, sans-serif; margin: 10mm; color: #111; }
  .sheet { display: grid; grid-template-columns: repeat(auto-fill, 70mm); gap: 3mm; }
  .label { box-sizing: border-box; width: 70mm; height: 34mm; display: flex; gap: 3mm; align-items: center;
           border: 1px dashed #bbb; padding: 3mm; break-inside: avoid; }
  .label svg { width: 27mm; height: 27mm; flex: none; }
  .text { display: flex; flex-direction: column; gap: 1mm; min-width: 0; }
  .hint { color: #555; font-size: 7.5pt; }
  span { display: block; color: #666; font-size: 7pt; text-transform: uppercase; letter-spacing: .04em; }
  code { font: 600 10pt ui-monospace, Menlo, monospace; white-space: nowrap; }
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
