/**
 * Reading the QR code on a tracker's label. Labels encode
 * cattracker://add-cat?device=<tracker id>&code=<claim code>; the same
 * parameters in an https:// or exp:// link are accepted too, so a later web
 * landing page or Expo Go link keeps working.
 */
export interface ClaimLabel {
  deviceUid: string;
  claimCode: string;
}

const TRACKER_UID_RE = /^[A-Za-z0-9_-]{3,64}$/;

/** Labels print the code in groups ("ABCD-EFGH-JKLM"); the stored code has none. */
export const normalizeClaimCode = (code: string) => code.replace(/[\s-]/g, '');

export function parseClaimQr(text: string): ClaimLabel | null {
  const trimmed = text.trim();
  const query = trimmed.includes('?') ? trimmed.slice(trimmed.indexOf('?') + 1) : null;
  if (!query || !/^(cattracker|https?|exps?):\/\//i.test(trimmed)) return null;
  const params = new URLSearchParams(query.split('#')[0]);
  const deviceUid = params.get('device')?.trim() ?? '';
  const claimCode = normalizeClaimCode(params.get('code') ?? '');
  if (!TRACKER_UID_RE.test(deviceUid) || claimCode.length < 10 || claimCode.length > 64) return null;
  return { deviceUid, claimCode };
}
