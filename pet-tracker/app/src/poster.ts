/**
 * "Missing cat" poster as an A4 HTML page, printed to PDF with expo-print.
 * The QR code opens the live share link, so neighbours see where the cat is
 * right now.
 */
import QRCodeCore from 'qrcode/lib/core/qrcode';

import { t } from './i18n';

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

/** QR code as an inline SVG (one path, so printers render it sharp). */
export function qrSvg(value: string, sizePx = 220): string {
  const { modules } = QRCodeCore.create(value, { errorCorrectionLevel: 'M' });
  const n = modules.size;
  let d = '';
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) if (modules.data[y * n + x]) d += `M${x + 2} ${y + 2}h1v1h-1z`;
  }
  const box = n + 4;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${sizePx}" height="${sizePx}" viewBox="0 0 ${box} ${box}" shape-rendering="crispEdges"><rect width="${box}" height="${box}" fill="#fff"/><path d="${d}" fill="#000"/></svg>`;
}

export interface PosterInput {
  name: string;
  photoUrl: string | null;
  color: string;
  description: string;
  lastSeen: string;
  phone: string;
  shareUrl: string | null;
}

export function posterHtml(p: PosterInput): string {
  const photo = p.photoUrl
    ? `<img class="photo" src="${esc(p.photoUrl)}"/>`
    : `<div class="photo none" style="background:${esc(p.color)}">${esc(p.name.slice(0, 1).toUpperCase())}</div>`;
  return `<!doctype html><html><head><meta charset="utf-8"/>
<style>
  @page { size: A4; margin: 14mm; }
  body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #0C1220; margin: 0; }
  .title { font-size: 64px; font-weight: 900; letter-spacing: -1px; text-align: center; color: #C21F2B; margin: 0 0 8px; }
  .name { font-size: 40px; font-weight: 800; text-align: center; margin: 0 0 16px; }
  .photo { display: block; width: 100%; height: 360px; object-fit: cover; border-radius: 16px; }
  .none { color: #fff; font-size: 160px; font-weight: 800; display: flex; align-items: center; justify-content: center; }
  .facts { font-size: 20px; line-height: 1.45; margin: 18px 0; }
  .call { background: #0C1220; color: #fff; border-radius: 16px; padding: 16px 20px; text-align: center; }
  .call .label { font-size: 18px; opacity: .8; }
  .call .phone { font-size: 44px; font-weight: 800; letter-spacing: 1px; }
  .live { display: flex; gap: 18px; align-items: center; margin-top: 18px; }
  .live p { font-size: 18px; line-height: 1.4; margin: 0; }
</style></head><body>
  <p class="title">${esc(t('MISSING CAT'))}</p>
  <p class="name">${esc(p.name)}</p>
  ${photo}
  <div class="facts">
    ${p.description ? `<div>${esc(p.description)}</div>` : ''}
    <div><b>${esc(t('Last seen'))}:</b> ${esc(p.lastSeen)}</div>
  </div>
  ${p.phone ? `<div class="call"><div class="label">${esc(t('Seen {name}? Please call', { name: p.name }))}</div><div class="phone">${esc(p.phone)}</div></div>` : ''}
  ${p.shareUrl ? `<div class="live">${qrSvg(p.shareUrl, 150)}<p>${esc(t('Scan to see where {name} is right now (live, from the collar).', { name: p.name }))}</p></div>` : ''}
</body></html>`;
}
