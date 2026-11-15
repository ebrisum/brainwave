/**
 * Links people send each other: a live share link for a lost cat and an
 * invite to a household or cat sitting. The web address comes from
 * EXPO_PUBLIC_WEB_URL (the web build of this app, hosted on your domain);
 * without it the app's own cattracker:// links are used.
 */
const WEB = (process.env.EXPO_PUBLIC_WEB_URL ?? '').replace(/\/+$/, '');
const SCHEME = 'cattracker://';

export const hasWebLinks = () => WEB !== '';

export function shareUrl(token: string): string {
  return WEB ? `${WEB}/share/${encodeURIComponent(token)}` : `${SCHEME}share/${encodeURIComponent(token)}`;
}

export function inviteUrl(code: string): string {
  return WEB ? `${WEB}/join?code=${encodeURIComponent(code)}` : `${SCHEME}join?code=${encodeURIComponent(code)}`;
}

/** The invite code inside a pasted or scanned invite link, or the text itself if it is a bare code. */
export function inviteCodeFrom(text: string): string | null {
  const s = text.trim();
  const m = /[?&]code=([A-Za-z0-9-]+)/.exec(s);
  if (m) return m[1]!.toUpperCase();
  return /^[A-Za-z0-9-]{4,32}$/.test(s) ? s.toUpperCase() : null;
}

/** Directions to a point in the phone's maps app (works on iOS, Android and web). */
export function directionsUrl(lat: number, lng: number, walking = true): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat.toFixed(6)},${lng.toFixed(6)}&travelmode=${walking ? 'walking' : 'driving'}`;
}

export const SUPPORT_EMAIL = process.env.EXPO_PUBLIC_SUPPORT_EMAIL ?? 'support@example.com';
export const PRIVACY_URL = process.env.EXPO_PUBLIC_PRIVACY_URL ?? (WEB ? `${WEB}/privacy` : '');
export const TERMS_URL = process.env.EXPO_PUBLIC_TERMS_URL ?? (WEB ? `${WEB}/terms` : '');
