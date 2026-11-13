/**
 * Password reset with the link from Supabase's standard e-mail, for when the
 * e-mail template has no 6-digit code. The person copies the link (or, if
 * they already opened it, the address the browser ended up on) and pastes it.
 *
 *   https://<ref>.supabase.co/auth/v1/verify?token=<hash>&type=recovery&redirect_to=…
 *       -> verifyOtp({ token_hash, type: 'recovery' })
 *   https://<site>/#access_token=…&refresh_token=…&type=recovery
 *       -> setSession(...)  (the link was already opened in a browser)
 */
export type RecoveryLink =
  | { kind: 'token_hash'; tokenHash: string }
  | { kind: 'session'; accessToken: string; refreshToken: string };

function params(text: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const part of text.split(/[?#&]/).slice(1)) {
    const eq = part.indexOf('=');
    if (eq <= 0) continue;
    try {
      out.set(decodeURIComponent(part.slice(0, eq)), decodeURIComponent(part.slice(eq + 1).replace(/\+/g, ' ')));
    } catch {
      // malformed escape: skip this part
    }
  }
  return out;
}

export function parseRecoveryLink(text: string): RecoveryLink | null {
  const trimmed = text.trim();
  if (!/^https?:\/\//i.test(trimmed)) return null;
  const p = params(trimmed);
  const access = p.get('access_token');
  const refresh = p.get('refresh_token');
  if (access && refresh) return { kind: 'session', accessToken: access, refreshToken: refresh };
  const hash = p.get('token_hash') ?? p.get('token');
  const type = p.get('type');
  if (hash && /^[A-Za-z0-9_-]{8,}$/.test(hash) && (!type || type === 'recovery')) return { kind: 'token_hash', tokenHash: hash };
  return null;
}
